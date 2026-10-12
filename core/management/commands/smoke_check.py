from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.utils import timezone

from accounts.models import Address, UserProfile
from cart.models import Cart, CartItem
from extras.models import BlogCategory, BlogPost, DoctorProfile, SupportTicket
from orders.models import Order
from products.models import Brand, Category, Product
from vendors.models import Vendor, VendorProduct


class Command(BaseCommand):
    help = "Run a broad smoke check across the main MediMart pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--use-existing",
            action="store_true",
            help="Use existing demo records instead of creating smoke-check records.",
        )

    def handle(self, *args, **options):
        use_existing = options["use_existing"]
        data = self.get_existing_data() if use_existing else self.create_smoke_data()
        usernames = {
            "customer": "customer" if use_existing else "medimart_smoke_customer",
            "vendor": "vendor" if use_existing else "medimart_smoke_vendor",
            "doctor": "doctor" if use_existing else "medimart_smoke_doctor",
            "staff": "admin" if use_existing else "medimart_smoke_staff",
        }
        password = "MediMart@2026" if use_existing else "Testpass123!"
        client = Client(HTTP_HOST="127.0.0.1")
        failures = []

        public_paths = [
            "/",
            "/products/",
            "/search/?q=smoke",
            f"/products/{data['product'].slug}/",
            f"/category/{data['category'].slug}/",
            "/medical-equipment/",
            "/surgical-equipment/",
            "/diagnostic-equipment/",
            f"/price-comparison/{data['product'].slug}/",
            f"/price-comparison/id/{data['product'].pk}/",
            f"/compare/?products={data['product'].pk}",
            "/vendors/",
            f"/vendor/{data['vendor'].pk}/",
            "/blog/",
            f"/blog/{data['post'].slug}/",
            "/doctors/",
        ]
        if data.get("doctor"):
            public_paths.append(f"/doctors/{data['doctor'].pk}/")
        self.check_paths(client, "public", public_paths, failures)

        self.login(client, usernames["customer"], password)
        customer_paths = [
            "/dashboard/",
            "/profile/",
            "/addresses/",
            "/addresses/add/",
            "/cart/",
            "/wishlist/",
            "/checkout/",
            "/orders/",
            "/prescriptions/",
            "/prescriptions/upload/",
            "/reviews/",
            "/notifications/",
            "/support/",
            "/support/create/",
            "/healthcare/",
            "/labs/",
            "/consultations/",
        ]
        self.check_paths(client, "customer", customer_paths, failures, accepted_statuses={"/checkout/": {200, 302}})
        client.logout()

        self.login(client, usernames["vendor"], password)
        vendor_paths = ["/vendor-dashboard/", "/vendor-products/", "/vendor-products/add/"]
        self.check_paths(client, "vendor", vendor_paths, failures)
        client.logout()

        if data.get("doctor") and get_user_model().objects.filter(username=usernames["doctor"], is_active=True).exists():
            self.login(client, usernames["doctor"], password)
            self.check_paths(client, "doctor", ["/doctor-dashboard/"], failures)
            client.logout()
        else:
            self.stdout.write(self.style.WARNING("doctor    skipped: no existing verified doctor demo account"))

        self.login(client, usernames["staff"], password)
        staff_paths = [
            "/admin/",
            "/admin-dashboard/",
            "/admin-dashboard/manage/users/",
            "/admin-dashboard/manage/products/",
            "/admin-dashboard/manage/categories/",
            "/admin-dashboard/manage/brands/",
            "/admin-dashboard/manage/vendors/",
            "/admin-dashboard/manage/licenses/",
            "/admin-dashboard/manage/offers/",
            "/admin-dashboard/manage/orders/",
            "/admin-dashboard/manage/prescriptions/",
            "/admin-dashboard/manage/coupons/",
            "/admin-dashboard/manage/doctors/",
            "/admin-dashboard/manage/blog/",
            "/admin-dashboard/manage/blog_categories/",
            "/admin-dashboard/manage/notifications/",
            "/delivery-dashboard/",
        ]
        self.check_paths(client, "staff", staff_paths, failures)
        client.logout()

        if failures:
            for label, path, status in failures:
                self.stderr.write(f"{label} {path} returned {status}")
            raise CommandError(f"Smoke check failed for {len(failures)} page(s).")

        self.stdout.write(self.style.SUCCESS("MediMart smoke check passed."))

    def check_paths(self, client, label, paths, failures, accepted_statuses=None):
        accepted_statuses = accepted_statuses or {}
        for path in paths:
            response = client.get(path)
            self.stdout.write(f"{label:8} {path:55} {response.status_code}")
            if response.status_code not in accepted_statuses.get(path, {200}):
                failures.append((label, path, response.status_code))

    def login(self, client, username, password):
        logged_in = client.login(username=username, password=password)
        if not logged_in:
            raise CommandError(f"Could not log in smoke user {username}.")

    def create_smoke_data(self):
        User = get_user_model()
        category, _ = Category.objects.get_or_create(
            name="Smoke Equipment",
            defaults={"slug": "smoke-equipment", "is_active": True},
        )
        brand, _ = Brand.objects.get_or_create(
            name="Smoke Health",
            defaults={"slug": "smoke-health", "is_active": True},
        )
        product, _ = Product.objects.update_or_create(
            sku="MM-SMOKE-001",
            defaults={
                "name": "MediMart Smoke Monitor",
                "slug": "medimart-smoke-monitor",
                "category": category,
                "brand": brand,
                "product_type": Product.ProductType.MEDICAL_EQUIPMENT,
                "description": "Smoke test medical equipment.",
                "short_description": "Smoke test monitor.",
                "mrp": Decimal("2000.00"),
                "selling_price": Decimal("1500.00"),
                "stock_quantity": 20,
                "manufacturer": "MediMart Smoke Labs",
                "is_active": True,
            },
        )

        customer = self.create_user("medimart_smoke_customer", "smoke.customer@gmail.com")
        UserProfile.objects.update_or_create(
            user=customer,
            defaults={"role": UserProfile.Role.CUSTOMER},
        )
        address, _ = Address.objects.get_or_create(
            user=customer,
            full_name="Smoke Customer",
            phone="9999999999",
            address_line_1="Smoke Street",
            city="Smoke City",
            state="Smoke State",
            pincode="123456",
            defaults={"is_default": True},
        )

        vendor_user = self.create_user("medimart_smoke_vendor", "smoke.vendor@gmail.com")
        UserProfile.objects.update_or_create(
            user=vendor_user,
            defaults={"role": UserProfile.Role.VENDOR},
        )
        vendor, _ = Vendor.objects.update_or_create(
            user=vendor_user,
            defaults={
                "business_name": "Smoke Pharmacy",
                "owner_name": "Smoke Owner",
                "email": "smoke.vendor@gmail.com",
                "phone": "8888888888",
                "address": "Smoke Vendor Street",
                "license_number": "SMOKE-LIC",
                "business_type": Vendor.BusinessType.PHARMACY,
                "is_approved": True,
                "is_active": True,
            },
        )
        offer, _ = VendorProduct.objects.update_or_create(
            vendor=vendor,
            product=product,
            defaults={
                "price": Decimal("1450.00"),
                "stock_quantity": 12,
                "delivery_time": "2 days",
                "warranty": "1 Year",
                "seller_rating": Decimal("4.50"),
                "is_active": True,
                "is_approved": True,
            },
        )

        doctor_user = self.create_user("medimart_smoke_doctor", "smoke.doctor@gmail.com")
        UserProfile.objects.update_or_create(
            user=doctor_user,
            defaults={"role": UserProfile.Role.DOCTOR},
        )
        doctor, _ = DoctorProfile.objects.update_or_create(
            user=doctor_user,
            defaults={
                "full_name": "Dr Smoke Doctor",
                "specialization": "General Medicine",
                "experience_years": 5,
                "clinic_name": "Smoke Clinic",
                "clinic_address": "Smoke Clinic Road",
                "consultation_fee": Decimal("500.00"),
                "availability": "Mon-Fri",
                "is_verified": True,
            },
        )

        staff = self.create_user("medimart_smoke_staff", "smoke.staff@gmail.com")
        staff.is_staff = True
        staff.is_superuser = True
        staff.save(update_fields=["is_staff", "is_superuser"])
        UserProfile.objects.update_or_create(
            user=staff,
            defaults={"role": UserProfile.Role.ADMIN},
        )

        blog_category, _ = BlogCategory.objects.get_or_create(
            name="Smoke Health Blog",
            defaults={"slug": "smoke-health-blog"},
        )
        post, _ = BlogPost.objects.update_or_create(
            slug="smoke-health-article",
            defaults={
                "title": "Smoke Health Article",
                "category": blog_category,
                "author": staff,
                "excerpt": "Smoke article.",
                "content": "Smoke article content.",
                "status": BlogPost.Status.PUBLISHED,
                "published_at": timezone.now(),
            },
        )

        order, _ = Order.objects.get_or_create(
            customer=customer,
            address=address,
            address_snapshot="Smoke Customer\nSmoke Street",
            subtotal=Decimal("1450.00"),
            discount=Decimal("0.00"),
            delivery_charge=Decimal("49.00"),
            total_amount=Decimal("1499.00"),
            payment_method=Order.PaymentMethod.COD,
            defaults={"order_status": Order.OrderStatus.SHIPPED},
        )
        order.order_status = Order.OrderStatus.SHIPPED
        order.save(update_fields=["order_status", "updated_at"])

        cart, _ = Cart.objects.get_or_create(user=customer)
        CartItem.objects.update_or_create(
            cart=cart,
            vendor_product=offer,
            defaults={"quantity": 1},
        )
        SupportTicket.objects.get_or_create(
            user=customer,
            subject="Smoke help",
            defaults={
                "category": SupportTicket.Category.ORDER,
                "message": "Smoke support ticket.",
            },
        )

        return {
            "category": category,
            "product": product,
            "vendor": vendor,
            "doctor": doctor,
            "post": post,
        }

    def get_existing_data(self):
        data = {
            "category": Category.objects.filter(slug="blood-pressure-monitors").first()
            or Category.objects.filter(products__isnull=False).first(),
            "product": Product.objects.filter(sku="MM-BP-001").first()
            or Product.objects.filter(is_active=True).first(),
            "vendor": Vendor.objects.filter(is_active=True, is_approved=True).first(),
            "doctor": DoctorProfile.objects.filter(is_verified=True).first(),
            "post": BlogPost.objects.filter(status=BlogPost.Status.PUBLISHED).first(),
        }
        # Existing installations may have real customer/vendor data without a
        # seeded doctor. Keep the smoke check useful while still testing every
        # role that is actually present.
        missing = [name for name, value in data.items() if value is None and name != "doctor"]
        if missing:
            raise CommandError(
                "Missing existing demo data for: "
                + ", ".join(missing)
                + ". Run `python manage.py reset_demo_data` first."
            )
        return data

    def create_user(self, username, email):
        User = get_user_model()
        user, _ = User.objects.get_or_create(username=username, defaults={"email": email})
        user.email = email
        user.set_password("Testpass123!")
        user.save()
        return user
