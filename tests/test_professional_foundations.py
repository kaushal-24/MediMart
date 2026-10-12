from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Address, UserProfile
from extras.models import DoctorProfile
from healthcare.models import ConsultationPayment, LabInvoice, LabPartner, LabTest


User = get_user_model()


class ProfessionalFoundationTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="foundation_customer",
            email="foundation.customer@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=self.customer, role=UserProfile.Role.CUSTOMER)
        self.address = Address.objects.create(
            user=self.customer,
            full_name="Foundation Customer",
            phone="9999999999",
            address_line_1="1 Test Street",
            city="Ahmedabad",
            state="Gujarat",
            pincode="380001",
        )
        self.partner = LabPartner.objects.create(
            name="Foundation Diagnostics",
            city="Ahmedabad",
            address="2 Lab Road",
            accreditations="NABL",
        )
        self.lab_test = LabTest.objects.create(
            partner=self.partner,
            name="Foundation Blood Profile",
            description="A test used by foundation workflow tests.",
            price=Decimal("299.00"),
            mrp=Decimal("399.00"),
        )
        doctor_user = User.objects.create_user(
            username="foundation_doctor",
            email="foundation.doctor@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=doctor_user, role=UserProfile.Role.DOCTOR)
        self.doctor = DoctorProfile.objects.create(
            user=doctor_user,
            full_name="Dr. Foundation Care",
            specialization="General Medicine",
            consultation_fee=Decimal("499.00"),
            is_verified=True,
        )

    def test_lab_booking_creates_a_customer_invoice_record(self):
        self.client.login(username="foundation_customer", password="Testpass123!")
        response = self.client.post(
            reverse("healthcare:lab_booking_for_test", args=[self.lab_test.pk]),
            {"lab_test": self.lab_test.pk, "address": self.address.pk},
        )
        self.assertRedirects(response, reverse("healthcare:lab_bookings"))
        invoice = LabInvoice.objects.get()
        self.assertEqual(invoice.subtotal, Decimal("299.00"))
        self.assertEqual(invoice.total_amount, Decimal("299.00"))

    def test_consultation_request_creates_a_payment_ledger_record(self):
        self.client.login(username="foundation_customer", password="Testpass123!")
        response = self.client.post(
            reverse("healthcare:consultation_create"),
            {
                "doctor": self.doctor.pk,
                "mode": "chat",
                "symptoms": "Routine consultation request",
                "patient_history": "",
                "consent_at": "2026-10-12T12:00",
                "scheduled_at": "",
            },
        )
        self.assertRedirects(response, reverse("healthcare:consultations"))
        payment = ConsultationPayment.objects.get()
        self.assertEqual(payment.amount, Decimal("499.00"))
        self.assertEqual(payment.status, ConsultationPayment.Status.PENDING)
