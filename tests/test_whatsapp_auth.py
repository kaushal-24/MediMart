import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


User = get_user_model()


@override_settings(
    WHATSAPP_PROVIDER="openwa",
    WHATSAPP_API_KEY="test-key",
    WHATSAPP_OTP_TTL_SECONDS=300,
    WHATSAPP_OTP_RESEND_COOLDOWN_SECONDS=0,
)
class WhatsAppAuthenticationTests(TestCase):
    @patch("accounts.views.send_whatsapp_message", return_value=True)
    def test_signup_requires_and_completes_whatsapp_verification(self, send_message):
        response = self.client.post(
            "/register/",
            {
                "username": "whatsapp-customer",
                "first_name": "Asha",
                "last_name": "Mehta",
                "email": "asha@example.com",
                "phone_number": "9876543210",
                "password1": "StrongPass!12345",
                "password2": "StrongPass!12345",
            },
        )
        self.assertRedirects(response, "/whatsapp/verify/")
        user = User.objects.get(username="whatsapp-customer")
        self.assertFalse(user.is_active)
        message = send_message.call_args.args[1]
        code = re.search(r"\b(\d{6})\b", message).group(1)
        self.assertIn(f"*{code}*", message)
        response = self.client.post("/whatsapp/verify/", {"code": code})
        self.assertRedirects(response, "/")
        self.assertTrue(User.objects.get(pk=user.pk).is_active)

    @patch("accounts.views.send_whatsapp_message", return_value=True)
    def test_login_does_not_require_whatsapp_verification(self, send_message):
        user = User.objects.create_user(
            username="whatsapp-login",
            email="login@example.com",
            password="StrongPass!12345",
            is_active=True,
        )
        from accounts.models import UserProfile

        UserProfile.objects.create(user=user, phone_number="9876543210")
        response = self.client.post("/login/", {"username": user.username, "password": "StrongPass!12345"})
        self.assertRedirects(response, "/")
        self.assertEqual(int(self.client.session.get("_auth_user_id")), user.pk)
        send_message.assert_not_called()

    @patch("accounts.views.send_whatsapp_message", return_value=True)
    def test_password_reset_uses_whatsapp_otp_before_setting_new_password(self, send_message):
        user = User.objects.create_user(
            username="whatsapp-reset",
            email="reset@example.com",
            password="OldStrongPass!12345",
            is_active=True,
        )
        from accounts.models import UserProfile

        UserProfile.objects.create(user=user, phone_number="9876543210")

        response = self.client.post("/password-reset/", {"phone_number": "9876543210"})
        self.assertRedirects(response, "/password-reset/verify/")
        self.assertTrue(send_message.called)
        self.assertIn("password reset code", send_message.call_args.args[1])
        message = send_message.call_args.args[1]
        code = re.search(r"\b(\d{6})\b", message).group(1)
        self.assertIn(f"*{code}*", message)

        response = self.client.post("/password-reset/verify/", {"code": code})
        self.assertRedirects(response, "/reset/confirm/")

        response = self.client.post(
            "/reset/confirm/",
            {"new_password1": "NewStrongPass!12345", "new_password2": "NewStrongPass!12345"},
        )
        self.assertRedirects(response, "/reset/done/")
        self.assertTrue(User.objects.get(pk=user.pk).check_password("NewStrongPass!12345"))
