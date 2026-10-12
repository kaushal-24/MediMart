from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile


User = get_user_model()


class LoginIdentifierTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="identifier_customer",
            email="identifier.customer@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(
            user=self.user,
            role=UserProfile.Role.CUSTOMER,
            phone_number="+91 98765 43210",
        )

    def login_with(self, identifier):
        return self.client.post(
            reverse("accounts:login"),
            {"username": identifier, "password": "Testpass123!"},
        )

    def test_login_accepts_username_email_and_phone(self):
        for identifier in ("identifier_customer", "IDENTIFIER.CUSTOMER@GMAIL.COM", "+919876543210"):
            self.client.logout()
            response = self.login_with(identifier)
            self.assertRedirects(response, reverse("core:home"))
            self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_page_exposes_password_toggle_and_identifier_hint(self):
        response = self.client.get(reverse("accounts:login"))

        self.assertContains(response, "Username, email, or phone number")
        self.assertContains(response, 'data-password-toggle="id_password"')

    def test_registration_pages_expose_password_toggles(self):
        customer_response = self.client.get(reverse("accounts:register"))
        professional_response = self.client.get(reverse("accounts:professional_register"))

        for response in (customer_response, professional_response):
            self.assertContains(response, 'data-password-toggle="id_password1"')
            self.assertContains(response, 'data-password-toggle="id_password2"')
