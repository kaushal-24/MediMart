import base64
import secrets
import time

import pyotp
import qrcode
from qrcode.image.svg import SvgPathImage
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
from .forms import (
    AddressForm,
    CustomerRegistrationForm,
    ProfessionalRegistrationForm,
    UserProfileForm,
)
from .models import Address, UserProfile


User = get_user_model()


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
        if profile and profile.mfa_enabled and profile.mfa_secret:
            self.request.session.cycle_key()
            self.request.session["mfa_pending_user_id"] = user.pk
            self.request.session["mfa_pending_at"] = int(time.time())
            self.request.session["mfa_pending_auth_hash"] = user.get_session_auth_hash()
            self.request.session["mfa_pending_nonce"] = secrets.token_urlsafe(24)
            self.request.session.set_expiry(300)
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
            login(request, user)
            messages.success(request, "Your MediMart account has been created.")
            return redirect("accounts:dashboard")
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
            login(request, user)
            messages.success(
                request,
                "Your professional account is ready. Complete the required verification to unlock regulated tools.",
            )
            return redirect("accounts:dashboard")
    else:
        form = ProfessionalRegistrationForm()

    return render(request, "accounts/professional_register.html", {"form": form})


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
