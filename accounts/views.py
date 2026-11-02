import base64
import hashlib
import hmac
import secrets
import time

import pyotp
import qrcode
from qrcode.image.svg import SvgPathImage
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from cart.models import Wishlist
from core.audit import record_audit
from core.throttling import rate_limit
from extras.services import send_whatsapp_message
from .forms import (
    AddressForm,
    CustomerRegistrationForm,
    ProfessionalRegistrationForm,
    StyledSetPasswordForm,
    UserProfileForm,
    WhatsAppPasswordResetRequestForm,
    _normalise_phone,
)
from .permissions import STAFF_MFA_ROLES
from .models import Address, UserProfile


User = get_user_model()


def _whatsapp_chat_id(phone_number):
    digits = "".join(character for character in str(phone_number or "") if character.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        return f"{digits}@c.us"
    if len(digits) == 10 and digits[0] in "6789":
        return f"91{digits}@c.us"
    return ""


def _resolve_whatsapp_phone(phone_number):
    """Resolve one active account by its normalized WhatsApp number only."""
    normalized = _normalise_phone(phone_number)
    if len(normalized) != 10:
        return None
    matches = [
        profile.user
        for profile in UserProfile.objects.select_related("user").filter(
            user__is_active=True,
            phone_number__isnull=False,
        )
        if _normalise_phone(profile.phone_number) == normalized
    ]
    return matches[0] if len(matches) == 1 else None


def _otp_digest(code):
    return hmac.new(
        str(settings.SECRET_KEY).encode("utf-8"),
        str(code).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _start_whatsapp_otp(request, user, purpose):
    profile = getattr(user, "profile", None)
    chat_id = _whatsapp_chat_id(getattr(profile, "phone_number", ""))
    if not chat_id:
        return False, "Add a valid Indian mobile number to use WhatsApp verification."
    if settings.WHATSAPP_PROVIDER != "openwa" or not settings.WHATSAPP_API_KEY:
        return False, "WhatsApp verification is not configured. Ask the site administrator to connect OpenWA."

    current = request.session.get("whatsapp_otp", {})
    last_sent = int(current.get("sent_at", 0) or 0)
    remaining = settings.WHATSAPP_OTP_RESEND_COOLDOWN_SECONDS - (int(time.time()) - last_sent)
    if current.get("user_id") == user.pk and current.get("purpose") == purpose and remaining > 0:
        return False, f"Please wait {remaining} seconds before requesting another code."

    code = f"{secrets.randbelow(1_000_000):06d}"
    text = (
        f"Your MediMart {purpose} verification code is:\n\n"
        f"*{code}*\n\n"
        f"It expires in {settings.WHATSAPP_OTP_TTL_SECONDS // 60} minutes. Do not share this code."
    )
    if not send_whatsapp_message(chat_id, text):
        return False, "We could not send a WhatsApp verification code. Please try again shortly."

    request.session["whatsapp_otp"] = {
        "user_id": user.pk,
        "purpose": purpose,
        "target": chat_id,
        "digest": _otp_digest(code),
        "sent_at": int(time.time()),
        "attempts": 0,
    }
    request.session.set_expiry(settings.WHATSAPP_OTP_TTL_SECONDS)
    return True, ""


def _whatsapp_otp_configured():
    return all(
        (
            settings.WHATSAPP_PROVIDER == "openwa",
            bool(settings.WHATSAPP_API_URL),
            bool(settings.WHATSAPP_API_KEY),
            bool(settings.WHATSAPP_SESSION_ID),
        )
    )


def _clear_whatsapp_otp(request):
    request.session.pop("whatsapp_otp", None)
    request.session.set_expiry(None)


def _mfa_qr_data_uri(provisioning_uri):
    """Build an inline QR image without persisting the MFA secret anywhere."""
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=4,
        image_factory=SvgPathImage,
    )
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    svg_bytes = qr.make_image().to_string()
    encoded = base64.b64encode(svg_bytes).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


class MediMartLoginView(LoginView):
    authentication_form = None

    def get_success_url(self):
        """Send every completed password login to the public home page."""
        return reverse("core:home")

    def form_valid(self, form):
        user = form.get_user()
        profile = getattr(user, "profile", None)
        requires_mfa_setup = bool(
            profile
            and settings.STAFF_MFA_REQUIRED
            and profile.role in STAFF_MFA_ROLES
            and not (profile.mfa_enabled and profile.mfa_secret)
        )
        if profile and (profile.mfa_enabled and profile.mfa_secret or requires_mfa_setup):
            self.request.session.cycle_key()
            self.request.session["mfa_pending_user_id"] = user.pk
            self.request.session["mfa_pending_at"] = int(time.time())
            self.request.session["mfa_pending_auth_hash"] = user.get_session_auth_hash()
            self.request.session["mfa_pending_nonce"] = secrets.token_urlsafe(24)
            self.request.session.set_expiry(300)
            if requires_mfa_setup:
                response = super().form_valid(form)
                return redirect("accounts:mfa_settings")
            return redirect("accounts:mfa_challenge")
        response = super().form_valid(form)
        record_audit(self.request, "account.login", user, "Account sign-in completed.")
        return response


@rate_limit("customer-register", 8, 60 * 60, methods={"POST"})
def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = CustomerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.is_active = False
            user.save(update_fields=["is_active"])
            sent, error = _start_whatsapp_otp(request, user, "signup")
            if sent:
                messages.info(request, "We sent a verification code to your WhatsApp number.")
                return redirect("accounts:whatsapp_otp_verify")
            user.delete()
            messages.error(request, error)
    else:
        form = CustomerRegistrationForm()

    return render(request, "accounts/register.html", {"form": form})


@rate_limit("professional-register", 5, 60 * 60, methods={"POST"})
def professional_register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if request.method == "POST":
        form = ProfessionalRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.is_active = False
            user.save(update_fields=["is_active"])
            sent, error = _start_whatsapp_otp(request, user, "signup")
            if sent:
                messages.info(request, "We sent a verification code to your WhatsApp number.")
                return redirect("accounts:whatsapp_otp_verify")
            user.delete()
            messages.error(request, error)
    else:
        form = ProfessionalRegistrationForm()

    return render(request, "accounts/professional_register.html", {"form": form})


@rate_limit("whatsapp-otp-verify", 10, 10 * 60, methods={"POST"})
def whatsapp_otp_verify(request):
    challenge = request.session.get("whatsapp_otp", {})
    user_id = challenge.get("user_id")
    purpose = challenge.get("purpose")
    if not user_id or purpose != "signup":
        messages.error(request, "Your WhatsApp verification session has expired.")
        return redirect("accounts:register")

    user = get_object_or_404(User, pk=user_id)
    age = int(time.time()) - int(challenge.get("sent_at", 0) or 0)
    if age > settings.WHATSAPP_OTP_TTL_SECONDS:
        _clear_whatsapp_otp(request)
        messages.error(request, "That WhatsApp verification code has expired. Please start again.")
        return redirect("accounts:register")

    if request.method == "POST" and request.POST.get("action") == "resend":
        sent, error = _start_whatsapp_otp(request, user, purpose)
        messages.success(request, "A new verification code was sent to WhatsApp.") if sent else messages.error(request, error)
        return redirect("accounts:whatsapp_otp_verify")

    if request.method == "POST":
        code = "".join(character for character in request.POST.get("code", "") if character.isdigit())
        attempts = int(challenge.get("attempts", 0) or 0) + 1
        challenge["attempts"] = attempts
        request.session["whatsapp_otp"] = challenge
        valid = len(code) == 6 and hmac.compare_digest(challenge.get("digest", ""), _otp_digest(code))
        if valid:
            if purpose == "signup":
                user.is_active = True
                user.save(update_fields=["is_active"])
                _clear_whatsapp_otp(request)
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                record_audit(request, "account.whatsapp_signup", user, "WhatsApp signup verification completed.")
                messages.success(request, "Your MediMart account has been verified.")
                return redirect("core:home")
        if attempts >= settings.WHATSAPP_OTP_MAX_ATTEMPTS:
            _clear_whatsapp_otp(request)
            messages.error(request, "Too many incorrect codes. Please start the verification again.")
            return redirect("accounts:register")
        messages.error(request, "That WhatsApp verification code is invalid.")

    profile = getattr(user, "profile", None)
    phone = str(getattr(profile, "phone_number", ""))
    masked_phone = f"••••••{phone[-4:]}" if len(phone) >= 4 else "your WhatsApp number"
    return render(request, "accounts/whatsapp_otp_verify.html", {"purpose": purpose, "masked_phone": masked_phone})


PASSWORD_RESET_SESSION_KEY = "whatsapp_password_reset"
PASSWORD_RESET_VERIFIED_KEY = "whatsapp_password_reset_verified"


def _clear_password_reset(request):
    request.session.pop(PASSWORD_RESET_SESSION_KEY, None)
    request.session.pop(PASSWORD_RESET_VERIFIED_KEY, None)
    request.session.set_expiry(None)


def _start_password_reset_otp(request, user):
    profile = getattr(user, "profile", None)
    chat_id = _whatsapp_chat_id(getattr(profile, "phone_number", ""))
    if not chat_id:
        return False, "This account does not have a valid WhatsApp number for password recovery."
    if not _whatsapp_otp_configured():
        return False, "WhatsApp password recovery is not configured. Ask the site administrator to connect OpenWA."

    current = request.session.get(PASSWORD_RESET_SESSION_KEY, {})
    last_sent = int(current.get("sent_at", 0) or 0)
    remaining = settings.WHATSAPP_OTP_RESEND_COOLDOWN_SECONDS - (int(time.time()) - last_sent)
    if current.get("user_id") == user.pk and remaining > 0:
        return False, f"Please wait {remaining} seconds before requesting another code."

    code = f"{secrets.randbelow(1_000_000):06d}"
    text = (
        f"Your MediMart password reset code is:\n\n"
        f"*{code}*\n\n"
        f"It expires in {settings.WHATSAPP_OTP_TTL_SECONDS // 60} minutes. Do not share this code."
    )
    if not send_whatsapp_message(chat_id, text):
        return False, "We could not send a WhatsApp password reset code. Please try again shortly."

    request.session[PASSWORD_RESET_SESSION_KEY] = {
        "user_id": user.pk,
        "target": chat_id,
        "digest": _otp_digest(code),
        "sent_at": int(time.time()),
        "attempts": 0,
    }
    request.session.pop(PASSWORD_RESET_VERIFIED_KEY, None)
    request.session.set_expiry(settings.WHATSAPP_OTP_TTL_SECONDS)
    return True, ""


def password_reset_request(request):
    if request.user.is_authenticated:
        return redirect("core:home")

    if request.method == "POST":
        form = WhatsAppPasswordResetRequestForm(request.POST)
        if form.is_valid():
            user = _resolve_whatsapp_phone(form.cleaned_data["phone_number"])
            if user and user.is_active:
                sent, error = _start_password_reset_otp(request, user)
                if sent:
                    messages.info(request, "We sent a password reset code to your WhatsApp number.")
                    return redirect("accounts:password_reset_verify")
                form.add_error(None, error)
            else:
                form.add_error(None, "If an active account matches, a WhatsApp password reset code can be sent.")
    else:
        form = WhatsAppPasswordResetRequestForm()
    return render(request, "registration/password_reset_form.html", {"form": form})


def password_reset_done(request):
    return render(request, "registration/password_reset_done.html")


@rate_limit("password-reset-whatsapp-verify", 10, 10 * 60, methods={"POST"})
def password_reset_verify(request):
    challenge = request.session.get(PASSWORD_RESET_SESSION_KEY, {})
    user_id = challenge.get("user_id")
    if not user_id:
        messages.error(request, "Your WhatsApp password reset session has expired. Please start again.")
        return redirect("accounts:password_reset")

    user = get_object_or_404(User, pk=user_id, is_active=True)
    age = int(time.time()) - int(challenge.get("sent_at", 0) or 0)
    if age > settings.WHATSAPP_OTP_TTL_SECONDS:
        _clear_password_reset(request)
        messages.error(request, "That WhatsApp code has expired. Please start again.")
        return redirect("accounts:password_reset")

    if request.method == "POST" and request.POST.get("action") == "resend":
        sent, error = _start_password_reset_otp(request, user)
        if sent:
            messages.success(request, "A new password reset code was sent to WhatsApp.")
        else:
            messages.error(request, error)
        return redirect("accounts:password_reset_verify")

    if request.method == "POST":
        code = "".join(character for character in request.POST.get("code", "") if character.isdigit())
        attempts = int(challenge.get("attempts", 0) or 0) + 1
        challenge["attempts"] = attempts
        request.session[PASSWORD_RESET_SESSION_KEY] = challenge
        valid = len(code) == 6 and hmac.compare_digest(challenge.get("digest", ""), _otp_digest(code))
        if valid:
            request.session.pop(PASSWORD_RESET_SESSION_KEY, None)
            request.session[PASSWORD_RESET_VERIFIED_KEY] = {
                "user_id": user.pk,
                "verified_at": int(time.time()),
            }
            request.session.set_expiry(settings.WHATSAPP_OTP_TTL_SECONDS)
            record_audit(request, "account.password_reset_otp", user, "WhatsApp password reset verification completed.")
            return redirect("accounts:password_reset_confirm")
        if attempts >= settings.WHATSAPP_OTP_MAX_ATTEMPTS:
            _clear_password_reset(request)
            messages.error(request, "Too many incorrect codes. Please start the password reset again.")
            return redirect("accounts:password_reset")
        messages.error(request, "That WhatsApp password reset code is invalid.")

    phone = str(getattr(getattr(user, "profile", None), "phone_number", ""))
    masked_phone = f"••••••{phone[-4:]}" if len(phone) >= 4 else "your WhatsApp number"
    return render(request, "registration/password_reset_verify.html", {"masked_phone": masked_phone})


def password_reset_confirm(request):
    verified = request.session.get(PASSWORD_RESET_VERIFIED_KEY, {})
    user_id = verified.get("user_id")
    verified_at = int(verified.get("verified_at", 0) or 0)
    if not user_id or int(time.time()) - verified_at > settings.WHATSAPP_OTP_TTL_SECONDS:
        _clear_password_reset(request)
        messages.error(request, "Your WhatsApp password reset verification has expired. Please start again.")
        return redirect("accounts:password_reset")

    user = get_object_or_404(User, pk=user_id, is_active=True)
    form = StyledSetPasswordForm(user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        _clear_password_reset(request)
        request.session.cycle_key()
        record_audit(request, "account.password_reset", user, "Password reset completed through WhatsApp OTP.")
        messages.success(request, "Your password has been reset. You can now sign in.")
        return redirect("accounts:password_reset_complete")
    return render(request, "registration/password_reset_confirm.html", {"form": form, "validlink": True})


def password_reset_complete(request):
    return render(request, "registration/password_reset_complete.html")


@login_required
def dashboard(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    recent_addresses = request.user.addresses.all()[:3]
    recent_orders = request.user.orders.all()[:5]
    vendor_profile = getattr(request.user, "vendor_profile", None)
    doctor_profile = getattr(request.user, "doctor_profile", None)
    try:
        wishlist_count = request.user.wishlist.items.count()
    except Wishlist.DoesNotExist:
        wishlist_count = 0

    return render(
        request,
        "accounts/dashboard.html",
        {
            "profile": profile,
            "recent_addresses": recent_addresses,
            "recent_orders": recent_orders,
            "address_count": request.user.addresses.count(),
            "order_count": request.user.orders.count(),
            "prescription_count": request.user.prescriptions.count(),
            "wishlist_count": wishlist_count,
            "review_count": request.user.reviews.count(),
            "vendor_profile": vendor_profile,
            "doctor_profile": doctor_profile,
        },
    )


@login_required
def profile(request):
    user_profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = UserProfileForm(
            request.POST,
            request.FILES,
            user=request.user,
            profile=user_profile,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("accounts:profile")
    else:
        form = UserProfileForm(user=request.user, profile=user_profile)

    return render(request, "accounts/profile.html", {"form": form})


@rate_limit("mfa-challenge", 8, 10 * 60, methods={"POST"})
def mfa_challenge(request):
    user_id = request.session.get("mfa_pending_user_id")
    pending_at = request.session.get("mfa_pending_at", 0)
    pending_auth_hash = request.session.get("mfa_pending_auth_hash", "")
    if not user_id or not pending_auth_hash or int(time.time()) - int(pending_at) > 300:
        request.session.pop("mfa_pending_user_id", None)
        request.session.pop("mfa_pending_at", None)
        request.session.pop("mfa_pending_auth_hash", None)
        request.session.pop("mfa_pending_nonce", None)
        messages.error(request, "Your sign-in verification expired. Please sign in again.")
        return redirect("accounts:login")
    user = get_object_or_404(User, pk=user_id, is_active=True)
    if not secrets.compare_digest(pending_auth_hash, user.get_session_auth_hash()):
        request.session.flush()
        messages.error(request, "Your sign-in session changed. Please sign in again.")
        return redirect("accounts:login")
    profile = getattr(user, "profile", None)
    if not profile or not profile.mfa_enabled or not profile.mfa_secret:
        request.session.flush()
        return redirect("accounts:login")
    if request.method == "POST":
        code = request.POST.get("code", "").replace(" ", "")
        if pyotp.TOTP(profile.mfa_secret).verify(code, valid_window=1):
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            request.session.pop("mfa_pending_user_id", None)
            request.session.pop("mfa_pending_at", None)
            request.session.pop("mfa_pending_auth_hash", None)
            request.session.pop("mfa_pending_nonce", None)
            request.session.set_expiry(None)
            record_audit(request, "account.mfa_login", user, "Two-factor login completed.")
            return redirect("core:home")
        messages.error(request, "That verification code is invalid.")
    return render(request, "accounts/mfa_challenge.html")


@login_required
@rate_limit("mfa-settings", 10, 60 * 60, methods={"POST"})
def mfa_settings(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    if profile.mfa_enabled:
        if request.method == "POST" and request.POST.get("action") == "disable":
            password = request.POST.get("password", "")
            code = request.POST.get("code", "").replace(" ", "")
            if request.user.check_password(password) and pyotp.TOTP(profile.mfa_secret).verify(code, valid_window=1):
                profile.mfa_enabled = False
                profile.mfa_secret = ""
                profile.save(update_fields=["mfa_enabled", "mfa_secret"])
                record_audit(request, "account.mfa_disabled", request.user, "Two-factor authentication disabled.")
                messages.success(request, "Two-factor authentication has been disabled.")
                return redirect("accounts:profile")
            messages.error(request, "Password or verification code is invalid.")
        return render(request, "accounts/mfa_settings.html", {"enabled": True})

    secret = request.session.get("mfa_setup_secret") or pyotp.random_base32()
    request.session["mfa_setup_secret"] = secret
    if request.method == "POST" and request.POST.get("action") == "enable":
        code = request.POST.get("code", "").replace(" ", "")
        if pyotp.TOTP(secret).verify(code, valid_window=1):
            profile.mfa_secret = secret
            profile.mfa_enabled = True
            profile.save(update_fields=["mfa_secret", "mfa_enabled"])
            request.session.pop("mfa_setup_secret", None)
            record_audit(request, "account.mfa_enabled", request.user, "Two-factor authentication enabled.")
            messages.success(request, "Two-factor authentication is now enabled.")
            return redirect("accounts:profile")
        messages.error(request, "That verification code is invalid.")
    label = request.user.email or request.user.username
    provisioning_uri = pyotp.TOTP(secret).provisioning_uri(name=label, issuer_name="MediMart")
    qr_code_data_uri = _mfa_qr_data_uri(provisioning_uri)
    return render(
        request,
        "accounts/mfa_settings.html",
        {
            "enabled": False,
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "qr_code_data_uri": qr_code_data_uri,
        },
    )


@login_required
def address_list(request):
    addresses = request.user.addresses.all()
    return render(request, "accounts/address_list.html", {"addresses": addresses})


@login_required
def address_create(request):
    if request.method == "POST":
        form = AddressForm(request.POST, user=request.user)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, "Address added successfully.")
            return redirect("accounts:address_list")
    else:
        form = AddressForm(user=request.user)

    return render(
        request,
        "accounts/address_form.html",
        {"form": form, "page_title": "Add Address"},
    )


@login_required
def address_update(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)

    if request.method == "POST":
        form = AddressForm(request.POST, instance=address, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Address updated successfully.")
            return redirect("accounts:address_list")
    else:
        form = AddressForm(instance=address, user=request.user)

    return render(
        request,
        "accounts/address_form.html",
        {"form": form, "page_title": "Edit Address"},
    )


@login_required
def address_delete(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)

    if request.method == "POST":
        try:
            address.delete()
        except ProtectedError:
            messages.error(
                request,
                "This address belongs to an existing order and must be retained as part of its record.",
            )
        else:
            messages.success(request, "Address deleted successfully.")
        return redirect("accounts:address_list")

    return render(request, "accounts/address_confirm_delete.html", {"address": address})
