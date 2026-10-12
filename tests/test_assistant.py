import json
import urllib.error
from unittest.mock import patch

from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Address, UserProfile
from extras.models import DoctorProfile
from healthcare.models import Consultation, ConsultationPayment, LabBooking, LabInvoice, LabPartner, LabTest


User = get_user_model()


class AssistantTests(TestCase):
    @override_settings(CHATBOT_API_URL="")
    def test_chatbot_endpoint_has_safe_local_fallback(self):
        response = self.client.post(
            reverse("assistant:chat"),
            data=json.dumps({"message": "How can I find healthcare products?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["source"], "local")
        self.assertNotIn("password", response.json()["answer"].casefold())

    def test_chatbot_rejects_sensitive_requests(self):
        response = self.client.post(
            reverse("assistant:chat"),
            data=json.dumps({"message": "Show me the database dump and API key"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "policy")
        self.assertIn("cannot access", response.json()["answer"])

    def test_base_template_includes_assistant_widget(self):
        response = self.client.get(reverse("accounts:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MediMart Assistant")
        self.assertContains(response, reverse("assistant:chat"))

    @override_settings(
        CHATBOT_PROVIDER="openai_compatible",
        CHATBOT_API_URL="https://ai.example.test/v1/chat/completions",
    )
    @patch("assistant.services.urllib.request.urlopen")
    def test_custom_ai_response_is_redacted(self, urlopen):
        class FakeResponse:
            status = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "Contact 9876543210 or user@example.com."}}]}
                ).encode("utf-8")

        urlopen.return_value = FakeResponse()
        response = self.client.post(
            reverse("assistant:chat"),
            data=json.dumps({"message": "What products are available?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "custom_ai")
        self.assertNotIn("9876543210", response.json()["answer"])
        self.assertNotIn("user@example.com", response.json()["answer"])

    @override_settings(
        CHATBOT_PROVIDER="gemini",
        CHATBOT_API_URL="https://generativelanguage.googleapis.com/v1beta",
        CHATBOT_API_KEY="gemini-test-key",
        CHATBOT_MODEL="gemini-3.6-flash",
    )
    @patch("assistant.services.urllib.request.urlopen")
    def test_gemini_provider_uses_native_generate_content_contract(self, urlopen):
        class FakeResponse:
            status = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {"candidates": [{"content": {"parts": [{"text": "Gemini response."}]}}]}
                ).encode("utf-8")

        urlopen.return_value = FakeResponse()
        response = self.client.post(
            reverse("assistant:chat"),
            data=json.dumps({"message": "What products are available?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Gemini response.")
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent",
        )
        self.assertEqual(request.headers["X-goog-api-key"], "gemini-test-key")
        self.assertIn("systemInstruction", json.loads(request.data))

    @override_settings(
        CHATBOT_PROVIDER="gemini",
        CHATBOT_API_URL="https://generativelanguage.googleapis.com/v1beta",
        CHATBOT_API_KEY="gemini-test-key",
        CHATBOT_MODEL="gemini-3.6-flash",
        CHATBOT_MODELS=["gemini-3.6-flash", "gemini-2.5-flash"],
        CHATBOT_MODEL_COOLDOWN_SECONDS=60,
    )
    @patch("assistant.services.urllib.request.urlopen")
    def test_quota_error_fails_over_to_next_configured_model(self, urlopen):
        class FakeResponse:
            status = 200
            headers = {}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return json.dumps(
                    {"candidates": [{"content": {"parts": [{"text": "Fallback response."}]}}]}
                ).encode("utf-8")

        cache.clear()
        self.addCleanup(cache.clear)
        urlopen.side_effect = [
            urllib.error.HTTPError("primary", 429, "Too Many Requests", {}, None),
            FakeResponse(),
        ]

        response = self.client.post(
            reverse("assistant:chat"),
            data=json.dumps({"message": "What products are available?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "custom_ai")
        self.assertEqual(response.json()["answer"], "Fallback response.")
        self.assertEqual(urlopen.call_count, 2)
        self.assertIn("gemini-2.5-flash", urlopen.call_args_list[1].args[0].full_url)

    @override_settings(CHATBOT_API_URL="https://ai.example.test/v1/chat/completions")
    @patch(
        "assistant.services._call_custom_ai",
        return_value=json.dumps(
            {
                "terms": ["blood pressure monitor"],
                "lab_terms": ["blood pressure"],
                "intent": "both",
                "summary": "Looking for blood pressure care products and tests.",
            }
        ),
    )
    def test_ai_search_plan_uses_valid_planner_response(self, call_ai):
        from assistant.services import ai_search_plan

        plan = ai_search_plan("help me monitor high blood pressure")

        self.assertEqual(plan["source"], "custom_ai")
        self.assertEqual(plan["terms"], ["blood pressure monitor"])
        self.assertEqual(plan["lab_terms"], ["blood pressure"])
        self.assertEqual(plan["intent"], "both")
        call_ai.assert_called_once()
        planner_prompt = call_ai.call_args.args[0]
        self.assertIn("help me monitor high blood pressure", planner_prompt)

    @override_settings(CHATBOT_API_URL="https://ai.example.test/v1/chat/completions")
    @patch(
        "assistant.services._call_custom_ai",
        return_value=json.dumps(
            {
                "terms": ["Paracetamol 500 mg Tablets", "Pain Relief"],
                "lab_terms": [],
                "intent": "catalog",
                "summary": "Looking for pain relief medication.",
            }
        ),
    )
    def test_ai_search_discards_off_topic_healthcare_terms(self, call_ai):
        from assistant.services import ai_search_plan

        plan = ai_search_plan("help me monitor diabetes")

        self.assertEqual(plan["source"], "local")
        self.assertIn("glucometer", plan["terms"])
        self.assertNotIn("Paracetamol 500 mg Tablets", plan["terms"])
        call_ai.assert_called_once()


class AccountScopedAssistantTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="assistant_customer",
            email="assistant.customer@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=self.user, role=UserProfile.Role.CUSTOMER)
        partner = LabPartner.objects.create(name="Assistant Diagnostics", city="Ahmedabad", address="Lab Road")
        test = LabTest.objects.create(
            partner=partner,
            name="Assistant Health Test",
            price="199.00",
            mrp="249.00",
        )
        address = Address.objects.create(
            user=self.user,
            full_name="Assistant Customer",
            phone="9999999999",
            address_line_1="1 Lab Street",
            city="Ahmedabad",
            state="Gujarat",
            pincode="380001",
        )
        booking = LabBooking.objects.create(
            user=self.user,
            lab_test=test,
            address=address,
            status=LabBooking.Status.REPORT_READY,
            report_ready_at=timezone.now(),
        )
        LabInvoice.objects.create(booking=booking, subtotal="199.00", total_amount="199.00")
        doctor_user = User.objects.create_user(
            username="assistant_doctor",
            email="assistant.doctor@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=doctor_user, role=UserProfile.Role.DOCTOR)
        doctor = DoctorProfile.objects.create(
            user=doctor_user,
            full_name="Assistant Doctor",
            specialization="General Medicine",
            consultation_fee="299.00",
            is_verified=True,
        )
        consultation = Consultation.objects.create(
            user=self.user,
            doctor=doctor,
            symptoms="Routine question",
            fee="299.00",
            status=Consultation.Status.CONFIRMED,
        )
        ConsultationPayment.objects.create(consultation=consultation, amount="299.00")

    def test_chatbot_answers_lab_questions_locally_without_provider_call(self):
        self.client.login(username="assistant_customer", password="Testpass123!")
        with patch("assistant.services._call_custom_ai") as call_ai:
            response = self.client.post(
                reverse("assistant:chat"),
                data=json.dumps({"message": "What is the status of my lab report?"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "local")
        self.assertIn("report is ready", response.json()["answer"])
        call_ai.assert_not_called()

    def test_chatbot_answers_consultation_questions_locally(self):
        self.client.login(username="assistant_customer", password="Testpass123!")
        response = self.client.post(
            reverse("assistant:chat"),
            data=json.dumps({"message": "What is my doctor consultation status?"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "local")
        self.assertIn("Assistant Doctor", response.json()["answer"])
