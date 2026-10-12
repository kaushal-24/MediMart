from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Address, UserProfile
from extras.models import DoctorProfile
from healthcare.models import LabBooking, LabCollectionSlot, LabPartner, LabSampleEvent, LabTest, MedicationReminder
from orders.models import Order, OrderItem, Refund, ReturnRequest
from orders.services import complete_refund
from products.models import Category, Product
from vendors.models import Vendor, VendorProduct


User = get_user_model()


class HealthcareWorkflowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            username="health_customer",
            email="health.customer@gmail.com",
            password="Testpass123!",
            first_name="Health",
            last_name="Customer",
        )
        UserProfile.objects.create(user=self.customer, role=UserProfile.Role.CUSTOMER, phone_number="9999999999")
        self.other = User.objects.create_user(
            username="health_other",
            email="health.other@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=self.other, role=UserProfile.Role.CUSTOMER)
        self.staff = User.objects.create_user(
            username="health_operations",
            email="health.operations@gmail.com",
            password="Testpass123!",
            is_staff=True,
        )
        UserProfile.objects.create(user=self.staff, role=UserProfile.Role.ADMIN)
        self.address = Address.objects.create(
            user=self.customer,
            full_name="Health Customer",
            phone="9999999999",
            address_line_1="1 Test Street",
            city="Bengaluru",
            state="Karnataka",
            pincode="560001",
        )
        self.partner = LabPartner.objects.create(
            name="MediMart Diagnostics",
            city="Bengaluru",
            address="2 Lab Road",
            accreditations="NABL",
        )
        self.lab_test = LabTest.objects.create(
            partner=self.partner,
            name="Complete Blood Count",
            description="Routine blood profile",
            sample_type="Blood",
            price=Decimal("399.00"),
            mrp=Decimal("499.00"),
        )
        self.doctor_user = User.objects.create_user(
            username="health_doctor",
            email="health.doctor@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=self.doctor_user, role=UserProfile.Role.DOCTOR)
        self.doctor = DoctorProfile.objects.create(
            user=self.doctor_user,
            full_name="Dr. Verified Care",
            specialization="General Medicine",
            consultation_fee=Decimal("499.00"),
            is_verified=True,
        )

    def login_customer(self):
        self.client.login(username="health_customer", password="Testpass123!")

    def test_healthcare_pages_render_with_shared_navigation(self):
        self.login_customer()
        for route in (
            "healthcare:dashboard",
            "healthcare:labs",
            "healthcare:lab_bookings",
            "healthcare:records",
            "healthcare:reminders",
            "healthcare:consultations",
        ):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 200, route)
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lab tests")
        self.assertContains(response, "Health workspace")

    def test_operations_center_manages_new_healthcare_queues(self):
        self.client.login(username="health_operations", password="Testpass123!")
        dashboard = self.client.get(reverse("dashboards:admin_dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Returns &amp; Refunds")
        for section, title in (("returns", "Returns &amp; Refunds"), ("lab_tests", "Lab Tests &amp; Packages"), ("lab_bookings", "Lab Bookings"), ("consultations", "Doctor Consultations")):
            response = self.client.get(reverse("dashboards:management_records", args=[section]))
            self.assertEqual(response.status_code, 200, section)
            self.assertContains(response, title)

    def test_lab_booking_is_bound_to_logged_in_customer(self):
        self.login_customer()
        response = self.client.post(
            reverse("healthcare:lab_booking_for_test", args=[self.lab_test.pk]),
            {"lab_test": self.lab_test.pk, "address": self.address.pk},
        )
        self.assertRedirects(response, reverse("healthcare:lab_bookings"))
        booking = LabBooking.objects.get()
        self.assertEqual(booking.user, self.customer)
        self.assertEqual(booking.address, self.address)

    def test_selected_lab_test_cannot_be_changed_from_test_booking_link(self):
        other_test = LabTest.objects.create(
            partner=self.partner,
            name="Vitamin D",
            description="Vitamin D test",
            sample_type="Blood",
            price=Decimal("299.00"),
            mrp=Decimal("399.00"),
        )
        self.login_customer()
        response = self.client.post(
            reverse("healthcare:lab_booking_for_test", args=[self.lab_test.pk]),
            {"lab_test": other_test.pk, "address": self.address.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(LabBooking.objects.exists())
        self.assertContains(response, "cannot be changed")

    def test_customer_can_cancel_lab_booking_and_release_slot_capacity(self):
        slot = LabCollectionSlot.objects.create(
            partner=self.partner,
            starts_at=timezone.now() + timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=1, minutes=30),
            capacity=1,
        )
        self.login_customer()
        response = self.client.post(
            reverse("healthcare:lab_booking_for_test", args=[self.lab_test.pk]),
            {"lab_test": self.lab_test.pk, "address": self.address.pk, "slot": slot.pk},
        )
        self.assertRedirects(response, reverse("healthcare:lab_bookings"))
        booking = LabBooking.objects.get()
        self.assertEqual(slot.__class__.objects.get(pk=slot.pk).booked_count, 1)

        response = self.client.post(reverse("healthcare:lab_booking_cancel", args=[booking.pk]))

        self.assertRedirects(response, reverse("healthcare:lab_bookings"))
        booking.refresh_from_db()
        slot.refresh_from_db()
        self.assertEqual(booking.status, LabBooking.Status.CANCELLED)
        self.assertEqual(slot.booked_count, 0)
        self.assertTrue(booking.sample_events.filter(event_type=LabSampleEvent.EventType.CANCELLED).exists())

    def test_customer_can_reschedule_lab_booking_without_overbooking(self):
        first_slot = LabCollectionSlot.objects.create(
            partner=self.partner,
            starts_at=timezone.now() + timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=1, minutes=30),
            capacity=1,
        )
        second_slot = LabCollectionSlot.objects.create(
            partner=self.partner,
            starts_at=timezone.now() + timedelta(days=2),
            ends_at=timezone.now() + timedelta(days=2, minutes=30),
            capacity=1,
        )
        self.login_customer()
        self.client.post(
            reverse("healthcare:lab_booking_for_test", args=[self.lab_test.pk]),
            {"lab_test": self.lab_test.pk, "address": self.address.pk, "slot": first_slot.pk},
        )
        booking = LabBooking.objects.get()

        response = self.client.post(
            reverse("healthcare:lab_booking_reschedule", args=[booking.pk]),
            {"slot": second_slot.pk},
        )

        self.assertRedirects(response, reverse("healthcare:lab_bookings"))
        booking.refresh_from_db()
        first_slot.refresh_from_db()
        second_slot.refresh_from_db()
        self.assertEqual(booking.slot_id, second_slot.pk)
        self.assertEqual(first_slot.booked_count, 0)
        self.assertEqual(second_slot.booked_count, 1)

    def test_health_record_download_is_owner_only(self):
        from healthcare.models import HealthRecord

        record = HealthRecord.objects.create(
            user=self.customer,
            title="Blood report",
            record_type=HealthRecord.RecordType.LAB_REPORT,
            document=SimpleUploadedFile("report.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
        )
        self.login_customer()
        self.assertEqual(self.client.get(reverse("core:health_record_file", args=[record.pk])).status_code, 200)
        self.client.logout()
        self.client.login(username="health_other", password="Testpass123!")
        self.assertEqual(self.client.get(reverse("core:health_record_file", args=[record.pk])).status_code, 403)

    def test_reminder_creation_and_toggle(self):
        self.login_customer()
        response = self.client.post(
            reverse("healthcare:reminders"),
            {
                "label": "Morning medicine",
                "dosage": "1 tablet",
                "frequency": "Daily",
                "next_due_at": (timezone.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("healthcare:reminders"))
        reminder = MedicationReminder.objects.get()
        self.assertEqual(self.client.post(reverse("healthcare:reminder_toggle", args=[reminder.pk])).status_code, 302)
        reminder.refresh_from_db()
        self.assertFalse(reminder.is_active)

    def test_consultation_request_uses_verified_doctor_fee(self):
        self.login_customer()
        response = self.client.post(
            reverse("healthcare:consultation_create"),
            {
                "doctor": self.doctor.pk,
                "mode": "chat",
                "symptoms": "Fever for two days",
                "patient_history": "No known allergies",
                "consent_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertRedirects(response, reverse("healthcare:consultations"))
        consultation = self.customer.consultations.get()
        self.assertEqual(consultation.fee, Decimal("499.00"))

    def test_verified_doctor_can_access_patient_consultation(self):
        consultation = self.customer.consultations.create(
            doctor=self.doctor,
            mode="chat",
            symptoms="Fever for two days",
            fee=Decimal("499.00"),
        )
        self.client.force_login(self.doctor_user)
        response = self.client.get(reverse("healthcare:consultation_detail", args=[consultation.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Patient symptoms")

    def test_return_request_is_only_available_after_delivery_and_owned_by_customer(self):
        category = Category.objects.create(name="Health supplies", slug="health-supplies")
        product = Product.objects.create(
            name="Digital Thermometer",
            slug="digital-thermometer",
            sku="THERMO-1",
            category=category,
            product_type=Product.ProductType.MEDICAL_EQUIPMENT,
            description="A thermometer",
            mrp=Decimal("500.00"),
            selling_price=Decimal("400.00"),
        )
        vendor_user = User.objects.create_user(
            username="health_vendor",
            email="health.vendor@gmail.com",
            password="Testpass123!",
        )
        UserProfile.objects.create(user=vendor_user, role=UserProfile.Role.VENDOR)
        vendor = Vendor.objects.create(
            user=vendor_user,
            business_name="MediMart Seller",
            owner_name="Seller",
            email="health.vendor@gmail.com",
            phone="8888888888",
            address="Seller Road",
            license_number="HEALTH-LIC-1",
            business_type=Vendor.BusinessType.GENERAL_HEALTHCARE,
            is_approved=True,
        )
        vendor_product = VendorProduct.objects.create(
            vendor=vendor,
            product=product,
            price=Decimal("400.00"),
            stock_quantity=2,
            is_active=True,
            is_approved=True,
        )
        order = Order.objects.create(
            customer=self.customer,
            order_number="MM-HEALTH-1",
            address=self.address,
            subtotal=Decimal("400.00"),
            total_amount=Decimal("400.00"),
            address_snapshot="Test address",
            payment_method=Order.PaymentMethod.COD,
            order_status=Order.OrderStatus.DELIVERED,
        )
        item = OrderItem.objects.create(
            order=order,
            vendor_product=vendor_product,
            vendor=vendor,
            product=product,
            product_name=product.name,
            seller_name="MediMart",
            sku=product.sku,
            quantity=1,
            unit_price=Decimal("400.00"),
            total_price=Decimal("400.00"),
        )
        self.login_customer()
        response = self.client.get(reverse("orders:return_create", args=[item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Request a return")
        response = self.client.post(
            reverse("orders:return_create", args=[item.pk]),
            {"reason": ReturnRequest.Reason.DAMAGED, "quantity": 1, "description": "Seal was damaged."},
        )
        self.assertRedirects(response, reverse("orders:return_list"))
        return_request = ReturnRequest.objects.get(order_item=item)
        self.assertEqual(return_request.refund_amount, Decimal("400.00"))
        self.assertEqual(return_request.quantity, 1)
        self.assertContains(self.client.get(reverse("orders:return_list")), "Digital Thermometer")

        self.client.logout()
        self.client.login(username="health_operations", password="Testpass123!")
        action_url = reverse("dashboards:management_record_action", args=["returns", return_request.pk])
        for action in ("review", "approve", "pickup", "received", "inspect_accept", "refund"):
            response = self.client.post(action_url, {"action": action})
            self.assertEqual(response.status_code, 302, action)
        return_request.refresh_from_db()
        refund = Refund.objects.get(return_request=return_request)
        self.assertEqual(return_request.status, ReturnRequest.Status.REFUND_PENDING)
        self.assertEqual(refund.status, Refund.Status.REQUESTED)
        complete_refund(refund)
        return_request.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(return_request.status, ReturnRequest.Status.COMPLETED)
        self.assertEqual(order.order_status, Order.OrderStatus.REFUNDED)

        self.client.logout()
        self.client.login(username="health_other", password="Testpass123!")
        self.assertEqual(self.client.get(reverse("orders:return_create", args=[item.pk])).status_code, 404)
