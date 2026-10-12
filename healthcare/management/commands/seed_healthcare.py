from decimal import Decimal

from django.core.management.base import BaseCommand

from healthcare.models import LabPartner, LabTest


class Command(BaseCommand):
    help = "Create idempotent MediMart demo lab catalogue."

    def handle(self, *args, **options):
        partners = [
            {
                "name": "MediMart Demo Diagnostics",
                "city": "Ahmedabad",
                "address": "Demo collection centre, Ahmedabad, Gujarat",
                "accreditations": "Demo catalogue - replace with verified partner accreditation",
                "phone": "18001234567",
            },
            {
                "name": "MediMart Demo Preventive Care",
                "city": "Bengaluru",
                "address": "Demo collection centre, Bengaluru, Karnataka",
                "accreditations": "Demo catalogue - partner verification required",
                "phone": "18001234567",
            },
        ]
        partner_map = {}
        for values in partners:
            partner, _ = LabPartner.objects.update_or_create(
                name=values["name"],
                city=values["city"],
                defaults=values,
            )
            partner_map[partner.city] = partner

        tests = [
            {
                "partner": partner_map["Ahmedabad"],
                "name": "Complete Blood Count (Demo)",
                "category": LabTest.Category.PACKAGE,
                "description": "Demo preventive package for local development and workflow testing.",
                "sample_type": "Blood",
                "preparation": "Follow the confirmed partner instructions before collection.",
                "report_sla_hours": 48,
                "price": Decimal("399.00"),
                "mrp": Decimal("499.00"),
            },
            {
                "partner": partner_map["Ahmedabad"],
                "name": "HbA1c Test (Demo)",
                "category": LabTest.Category.TEST,
                "description": "Demo individual test for booking and report-status workflows.",
                "sample_type": "Blood",
                "preparation": "No preparation guidance is confirmed until a real partner is onboarded.",
                "report_sla_hours": 24,
                "price": Decimal("299.00"),
                "mrp": Decimal("399.00"),
            },
            {
                "partner": partner_map["Bengaluru"],
                "name": "Thyroid Profile (Demo)",
                "category": LabTest.Category.PACKAGE,
                "description": "Demo package for customer discovery and slot-request testing.",
                "sample_type": "Blood",
                "preparation": "The verified partner should confirm fasting and collection instructions.",
                "report_sla_hours": 36,
                "price": Decimal("549.00"),
                "mrp": Decimal("699.00"),
            },
        ]
        for values in tests:
            LabTest.objects.update_or_create(
                partner=values["partner"],
                name=values["name"],
                defaults=values,
            )

        self.stdout.write(self.style.SUCCESS("MediMart demo lab catalogue created or updated."))
