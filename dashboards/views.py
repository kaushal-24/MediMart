from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import UserProfile
from accounts.permissions import (
    CAPABILITY_ROLES,
    OPERATIONS_ROLES,
    has_capability,
    role_required,
)
from core.audit import record_audit
from orders.views import CheckoutStockError, finalize_order_inventory_sale
from orders.services import activate_recall_notice, create_return_refund, restock_return_inventory
from orders.models import (
    Coupon,
    InventoryBatch,
    InventoryTemperatureLog,
    Order,
    OrderStatusHistory,
    Payment,
    RecallNotice,
    DispensingRecord,
    Refund,
    ReturnRequest,
    Shipment,
    ShipmentEvent,
    Warehouse,
)
from prescriptions.models import Prescription
from products.models import Brand, Category, Product
from extras.models import (
    BlogCategory,
    BlogPost,
    DoctorProfile,
    PharmacistProfile,
    QualityComplaint,
    Notification,
    NotificationDelivery,
    SupportTicket,
)
from core.models import AuditEvent
from extras.services import create_notification
from vendors.models import BusinessLicense, Vendor, VendorProduct
from healthcare.models import Consultation, LabBooking, LabCollectionSlot, LabPartner, LabTest

from .forms import (
    BlogManagementForm,
    BlogCategoryManagementForm,
    BrandManagementForm,
    CategoryManagementForm,
    CouponManagementForm,
    ProductManagementForm,
    InventoryBatchManagementForm,
    InventoryTemperatureLogManagementForm,
    RecallNoticeManagementForm,
    PharmacistProfileManagementForm,
    QualityComplaintManagementForm,
    DispensingRecordManagementForm,
    LabBookingManagementForm,
    LabCollectionSlotManagementForm,
    LabPartnerManagementForm,
    ShipmentManagementForm,
    LabTestManagementForm,
    ConsultationManagementForm,
    DoctorManagementForm,
    BusinessLicenseManagementForm,
    NotificationManagementForm,
    OrderManagementForm,
    PaymentManagementForm,
    RefundManagementForm,
    ReturnRequestManagementForm,
    UserManagementForm,
    VendorManagementForm,
    VendorProductManagementForm,
    WarehouseManagementForm,
)

User = get_user_model()


def _linked_return_refund(return_request):
    try:
        return return_request.refund
    except Refund.DoesNotExist:
        return None


SECTION_CAPABILITIES = {
    "users": "users.manage",
    "products": "catalog.manage",
    "categories": "catalog.manage",
    "brands": "catalog.manage",
    "offers": "catalog.manage",
    "blog": "catalog.manage",
    "blog_categories": "catalog.manage",
    "vendors": "seller.manage",
    "licenses": "compliance.review",
    "doctors": "clinical.doctor_operations",
    "pharmacists": "clinical.manage",
    "prescriptions": "clinical.prescription_review",
    "dispensing": "clinical.prescription_review",
    "quality_complaints": "support.manage",
    "lab_tests": "clinical.lab_operations",
    "lab_partners": "clinical.lab_operations",
    "consultations": "clinical.manage",
    "lab_bookings": "clinical.lab_operations",
    "lab_slots": "clinical.lab_operations",
    "support": "support.manage",
    "notifications": "support.manage",
    "notification_deliveries": "support.manage",
    "returns": "support.manage",
    "orders": "fulfillment.manage",
    "warehouses": "fulfillment.manage",
    "inventory": "fulfillment.manage",
    "temperature_logs": "fulfillment.manage",
    "recalls": "compliance.review",
    "shipments": "fulfillment.manage",
    "payments": "finance.manage",
    "refunds": "finance.manage",
    "coupons": "finance.manage",
    "audit": "audit.view",
}

# Backwards-compatible role sets for integrations that import SECTION_RULES.
SECTION_RULES = {
    section: CAPABILITY_ROLES[capability]
    for section, capability in SECTION_CAPABILITIES.items()
}


def management_section_allowed(user, section):
    capability = SECTION_CAPABILITIES.get(section)
    return bool(capability and has_capability(user, capability))


def management_row(record, values, status_label="", status="", actions=None, edit_url="", view_url=""):
    return {
        "pk": record.pk,
        "values": values,
        "status_label": status_label,
        "status": status,
        "actions": actions or [],
        "edit_url": edit_url,
        "view_url": view_url,
        "delete_url": "",
    }


@role_required(*OPERATIONS_ROLES, allow_staff=True)
def admin_dashboard(request):
    today = timezone.localdate()
    monthly_orders = Order.objects.filter(
        created_at__year=today.year,
        created_at__month=today.month,
    )
    return _render_admin_dashboard(request, today, monthly_orders)


@role_required(*OPERATIONS_ROLES, allow_staff=True)
def management_records(request, section):
    if not management_section_allowed(request.user, section):
        raise PermissionDenied
    if section == "support":
        return redirect("extras:support_ticket_list")

    query = request.GET.get("q", "").strip()
    title = section.replace("_", " ").title()
    description = "Search, review, and manage MediMart operational records."
    columns = []
    create_url = ""
    create_label = ""

    if section == "users":
        records = User.objects.select_related("profile").order_by("-date_joined")
        if query:
            records = records.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )
        columns = ["Account", "Email", "Role", "Joined"]
        create_url = reverse("dashboards:management_create", args=["users"])
        create_label = "user"
    elif section == "products":
        records = Product.objects.select_related("category", "brand").order_by("name")
        if query:
            records = records.filter(Q(name__icontains=query) | Q(sku__icontains=query))
        columns = ["Product", "Category", "Price", "Stock"]
        create_url = reverse("dashboards:management_create", args=["products"])
        create_label = "product"
    elif section == "categories":
        records = Category.objects.select_related("parent").annotate(product_count=Count("products")).order_by("name")
        if query:
            records = records.filter(name__icontains=query)
        columns = ["Category", "Parent", "Products", "Updated"]
        create_url = reverse("dashboards:management_create", args=["categories"])
        create_label = "category"
    elif section == "brands":
        records = Brand.objects.annotate(product_count=Count("products")).order_by("name")
        if query:
            records = records.filter(name__icontains=query)
        columns = ["Brand", "Products", "Description", "Updated"]
        create_url = reverse("dashboards:management_create", args=["brands"])
        create_label = "brand"
    elif section == "vendors":
        records = Vendor.objects.select_related("user").order_by("business_name")
        if query:
            records = records.filter(Q(business_name__icontains=query) | Q(email__icontains=query) | Q(license_number__icontains=query))
        title = "Sellers"
        columns = ["Business", "Type", "Contact", "Licence"]
        create_url = reverse("dashboards:management_create", args=["vendors"])
        create_label = "seller"
    elif section == "licenses":
        records = BusinessLicense.objects.select_related("vendor", "reviewed_by").order_by("-updated_at")
        if query:
            records = records.filter(Q(license_number__icontains=query) | Q(vendor__business_name__icontains=query) | Q(legal_name__icontains=query))
        title = "Business Licences"
        columns = ["Business", "Licence", "Type", "Last reviewed"]
        create_url = reverse("dashboards:management_create", args=["licenses"])
        create_label = "licence"
    elif section == "offers":
        records = VendorProduct.objects.select_related("product", "vendor").order_by("product__name")
        if query:
            records = records.filter(Q(product__name__icontains=query) | Q(vendor__business_name__icontains=query))
        title = "Seller Offers"
        columns = ["Product", "Seller", "Price", "Stock"]
        create_url = reverse("dashboards:management_create", args=["offers"])
        create_label = "seller offer"
    elif section == "orders":
        records = Order.objects.select_related("customer", "delivery_staff").order_by("-created_at")
        if query:
            records = records.filter(Q(order_number__icontains=query) | Q(customer__username__icontains=query))
        columns = ["Order", "Customer", "Total", "Delivery owner"]
    elif section == "prescriptions":
        records = Prescription.objects.select_related("user", "reviewed_by").order_by("-created_at")
        if query:
            records = records.filter(Q(user__username__icontains=query) | Q(doctor_name__icontains=query))
        columns = ["Prescription", "Customer", "Doctor", "Uploaded"]
    elif section == "dispensing":
        records = DispensingRecord.objects.select_related("order_item__order", "pharmacist", "batch").order_by("-dispensed_at")
        if query:
            records = records.filter(Q(order_item__order__order_number__icontains=query) | Q(pharmacist__username__icontains=query) | Q(batch__batch_number__icontains=query))
        title = "Dispensing Records"
        columns = ["Order", "Pharmacist", "Batch", "Quantity"]
        create_url = reverse("dashboards:management_create", args=["dispensing"])
        create_label = "dispensing record"
    elif section == "quality_complaints":
        records = QualityComplaint.objects.select_related("user", "product", "order", "reviewed_by").order_by("-created_at")
        if query:
            records = records.filter(Q(product__name__icontains=query) | Q(user__username__icontains=query) | Q(batch_number__icontains=query) | Q(description__icontains=query))
        title = "Quality Complaints"
        columns = ["Product", "Customer", "Batch", "Created"]
        create_url = reverse("dashboards:management_create", args=["quality_complaints"])
        create_label = "quality complaint"
    elif section == "coupons":
        records = Coupon.objects.order_by("code")
        if query:
            records = records.filter(code__icontains=query)
        columns = ["Code", "Discount", "Minimum order", "Validity"]
        create_url = reverse("dashboards:management_create", args=["coupons"])
        create_label = "coupon"
    elif section == "doctors":
        records = DoctorProfile.objects.select_related("user").order_by("full_name")
        if query:
            records = records.filter(Q(full_name__icontains=query) | Q(specialization__icontains=query))
        columns = ["Doctor", "Specialization", "Experience", "Clinic"]
        create_url = reverse("dashboards:management_create", args=["doctors"])
        create_label = "doctor"
    elif section == "pharmacists":
        records = PharmacistProfile.objects.select_related("user", "verified_by").order_by("full_name")
        if query:
            records = records.filter(Q(full_name__icontains=query) | Q(registration_number__icontains=query) | Q(pharmacy_name__icontains=query) | Q(pharmacy_license_number__icontains=query))
        title = "Pharmacists"
        columns = ["Pharmacist", "Registration", "Pharmacy", "State"]
        create_url = reverse("dashboards:management_create", args=["pharmacists"])
        create_label = "pharmacist"
    elif section == "blog":
        records = BlogPost.objects.select_related("category", "author").order_by("-updated_at")
        if query:
            records = records.filter(Q(title__icontains=query) | Q(category__name__icontains=query))
        title = "Health Guides"
        columns = ["Article", "Category", "Author", "Updated"]
        create_url = reverse("dashboards:management_create", args=["blog"])
        create_label = "health guide"
    elif section == "blog_categories":
        records = BlogCategory.objects.annotate(post_count=Count("posts")).order_by("name")
        if query:
            records = records.filter(name__icontains=query)
        title = "Guide Categories"
        columns = ["Category", "Articles", "Description", "Slug"]
        create_url = reverse("dashboards:management_create", args=["blog_categories"])
        create_label = "guide category"
    elif section == "notifications":
        records = Notification.objects.select_related("user").order_by("-created_at")
        if query:
            records = records.filter(Q(title__icontains=query) | Q(user__username__icontains=query))
        columns = ["Notification", "Recipient", "Type", "Created"]
        create_url = reverse("dashboards:management_create", args=["notifications"])
        create_label = "notification"
    elif section == "notification_deliveries":
        records = NotificationDelivery.objects.filter(channel=NotificationDelivery.Channel.EMAIL).select_related("notification", "notification__user").order_by("-created_at")
        if query:
            records = records.filter(Q(destination__icontains=query) | Q(notification__title__icontains=query))
        title = "Email Delivery"
        columns = ["Notification", "Destination", "Attempts", "Next attempt"]
    elif section == "payments":
        records = Payment.objects.select_related("order", "order__customer").order_by("-created_at")
        if query:
            records = records.filter(Q(order__order_number__icontains=query) | Q(gateway_payment_id__icontains=query))
        columns = ["Order", "Customer", "Amount", "Gateway reference"]
    elif section == "refunds":
        records = Refund.objects.select_related("payment__order", "requested_by").order_by("-created_at")
        if query:
            records = records.filter(Q(payment__order__order_number__icontains=query) | Q(gateway_refund_id__icontains=query))
        columns = ["Order", "Amount", "Reason", "Gateway reference"]
    elif section == "warehouses":
        records = Warehouse.objects.order_by("code")
        if query:
            records = records.filter(Q(code__icontains=query) | Q(name__icontains=query) | Q(pincode__icontains=query))
        columns = ["Code", "Warehouse", "Pincode", "Address"]
        create_url = reverse("dashboards:management_create", args=["warehouses"])
        create_label = "warehouse"
    elif section == "inventory":
        records = InventoryBatch.objects.select_related("vendor_product__product", "vendor_product__vendor", "warehouse").order_by("expires_on", "batch_number")
        if query:
            records = records.filter(Q(batch_number__icontains=query) | Q(vendor_product__product__name__icontains=query) | Q(warehouse__name__icontains=query))
        columns = ["Product", "Warehouse", "Quantity", "Expiry"]
        create_url = reverse("dashboards:management_create", args=["inventory"])
        create_label = "inventory batch"
    elif section == "temperature_logs":
        records = InventoryTemperatureLog.objects.select_related("batch", "recorded_by").order_by("-recorded_at")
        if query:
            records = records.filter(Q(batch__batch_number__icontains=query) | Q(source__icontains=query) | Q(note__icontains=query))
        title = "Temperature Logs"
        columns = ["Batch", "Temperature", "Recorded", "Source"]
        create_url = reverse("dashboards:management_create", args=["temperature_logs"])
        create_label = "temperature reading"
    elif section == "recalls":
        records = RecallNotice.objects.select_related("product", "batch", "initiated_by").order_by("-created_at")
        if query:
            records = records.filter(Q(reference__icontains=query) | Q(product__name__icontains=query) | Q(reason__icontains=query))
        title = "Product Recalls"
        columns = ["Reference", "Product", "Batch", "Created"]
        create_url = reverse("dashboards:management_create", args=["recalls"])
        create_label = "recall notice"
    elif section == "shipments":
        records = Shipment.objects.select_related("order", "warehouse").order_by("-updated_at")
        if query:
            records = records.filter(Q(order__order_number__icontains=query) | Q(tracking_number__icontains=query) | Q(courier_name__icontains=query))
        columns = ["Order", "Courier", "Tracking", "Promised"]
        create_url = reverse("dashboards:management_create", args=["shipments"])
        create_label = "shipment"
    elif section == "returns":
        records = ReturnRequest.objects.select_related(
            "order_item__order",
            "order_item__product",
            "order_item__dispensed_batch",
            "user",
            "reviewed_by",
            "inspected_by",
            "refund",
        ).order_by("-requested_at")
        if query:
            records = records.filter(Q(order_item__order__order_number__icontains=query) | Q(order_item__product_name__icontains=query) | Q(user__username__icontains=query))
        title = "Returns & Refunds"
        columns = ["Order", "Customer", "Item", "Reason"]
    elif section == "lab_tests":
        records = LabTest.objects.select_related("partner").order_by("name")
        if query:
            records = records.filter(Q(name__icontains=query) | Q(partner__name__icontains=query) | Q(partner__city__icontains=query))
        title = "Lab Tests & Packages"
        columns = ["Test", "Partner", "Price", "Collection"]
        create_url = reverse("dashboards:management_create", args=["lab_tests"])
        create_label = "lab test"
    elif section == "lab_partners":
        records = LabPartner.objects.order_by("name", "city")
        if query:
            records = records.filter(Q(name__icontains=query) | Q(city__icontains=query))
        title = "Lab Partners"
        columns = ["Partner", "City", "Accreditations", "Phone"]
        create_url = reverse("dashboards:management_create", args=["lab_partners"])
        create_label = "lab partner"
    elif section == "lab_bookings":
        records = LabBooking.objects.select_related("user", "lab_test", "lab_test__partner", "dependent").order_by("-created_at")
        if query:
            records = records.filter(Q(user__username__icontains=query) | Q(lab_test__name__icontains=query) | Q(accession_number__icontains=query))
        title = "Lab Bookings"
        columns = ["Booking", "Customer", "Test", "Slot"]
    elif section == "lab_slots":
        records = LabCollectionSlot.objects.select_related("partner").order_by("starts_at")
        if query:
            records = records.filter(Q(partner__name__icontains=query) | Q(starts_at__icontains=query))
        title = "Lab Collection Slots"
        columns = ["Partner", "Starts", "Ends", "Capacity"]
        create_url = reverse("dashboards:management_create", args=["lab_slots"])
        create_label = "collection slot"
    elif section == "consultations":
        records = Consultation.objects.select_related("user", "doctor", "dependent").order_by("-created_at")
        if query:
            records = records.filter(Q(user__username__icontains=query) | Q(doctor__full_name__icontains=query) | Q(symptoms__icontains=query))
        title = "Doctor Consultations"
        columns = ["Customer", "Doctor", "Mode", "Scheduled"]
    elif section == "audit":
        records = AuditEvent.objects.select_related("actor").order_by("-created_at")
        if query:
            records = records.filter(Q(action__icontains=query) | Q(target_type__icontains=query) | Q(summary__icontains=query))
        title = "Audit Trail"
        columns = ["Action", "Actor", "Target", "Summary"]
    else:
        raise PermissionDenied

    paginator = Paginator(records, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    rows = []
    for record in page_obj.object_list:
        if section == "users":
            role = getattr(getattr(record, "profile", None), "get_role_display", lambda: "Unassigned")()
            actions = [] if record == request.user else [("deactivate" if record.is_active else "activate", "Deactivate" if record.is_active else "Activate", "outline-danger" if record.is_active else "success")]
            rows.append(management_row(record, [record.get_full_name() or record.username, record.email, role, record.date_joined.strftime("%d %b %Y")], "Active" if record.is_active else "Inactive", "active" if record.is_active else "inactive", actions, reverse("dashboards:management_edit", args=["users", record.pk])))
        elif section == "products":
            actions = [("deactivate" if record.is_active else "activate", "Hide" if record.is_active else "Publish", "outline-danger" if record.is_active else "success"), ("unfeature" if record.is_featured else "feature", "Unfeature" if record.is_featured else "Feature", "outline-secondary")]
            rows.append(management_row(record, [f"{record.name} · {record.sku}", record.category.name, f"₹{record.selling_price}", str(record.stock_quantity)], "Published" if record.is_active else "Hidden", "active" if record.is_active else "inactive", actions, reverse("dashboards:management_edit", args=["products", record.pk])))
        elif section == "categories":
            rows.append(management_row(record, [record.name, record.parent.name if record.parent else "Top level", str(record.product_count), record.updated_at.strftime("%d %b %Y")], "Active" if record.is_active else "Inactive", "active" if record.is_active else "inactive", [("deactivate" if record.is_active else "activate", "Deactivate" if record.is_active else "Activate", "outline-danger" if record.is_active else "success")], reverse("dashboards:management_edit", args=["categories", record.pk])))
        elif section == "brands":
            rows.append(management_row(record, [record.name, str(record.product_count), record.description[:80] or "No description", record.updated_at.strftime("%d %b %Y")], "Active" if record.is_active else "Inactive", "active" if record.is_active else "inactive", [("deactivate" if record.is_active else "activate", "Deactivate" if record.is_active else "Activate", "outline-danger" if record.is_active else "success")], reverse("dashboards:management_edit", args=["brands", record.pk])))
        elif section == "vendors":
            rows.append(management_row(record, [record.business_name, record.get_business_type_display(), f"{record.email} · {record.phone}", record.license_number], "Approved" if record.is_approved and record.is_active else "Suspended", "active" if record.is_approved and record.is_active else "inactive", [("suspend" if record.is_active else "activate", "Suspend" if record.is_active else "Activate", "outline-danger" if record.is_active else "success")], edit_url=reverse("dashboards:management_edit", args=["vendors", record.pk])))
        elif section == "licenses":
            rows.append(management_row(record, [record.vendor.business_name, f"{record.license_number} · {record.form_number or 'Form pending'}", record.get_license_type_display(), record.reviewed_at.strftime("%d %b %Y") if record.reviewed_at else "Not reviewed"], record.get_status_display(), record.status, edit_url=reverse("dashboards:management_edit", args=["licenses", record.pk]), view_url=reverse("core:license_document", args=[record.pk]) if record.document else ""))
        elif section == "offers":
            rows.append(management_row(record, [record.product.name, record.vendor.business_name, f"₹{record.price}", str(record.stock_quantity)], "Live" if record.is_active and record.is_approved else "Review required", "active" if record.is_active and record.is_approved else "pending", [("deactivate" if record.is_active else "activate", "Disable" if record.is_active else "Publish", "outline-danger" if record.is_active else "success")], edit_url=reverse("dashboards:management_edit", args=["offers", record.pk])))
        elif section == "orders":
            rows.append(management_row(record, [record.order_number, record.customer.get_full_name() or record.customer.username, f"₹{record.total_amount}", record.delivery_staff.get_full_name() if record.delivery_staff else "Unassigned"], record.get_order_status_display(), record.order_status, edit_url=reverse("dashboards:management_edit", args=["orders", record.pk])))
        elif section == "prescriptions":
            actions = [] if record.status == Prescription.Status.APPROVED else [("approve", "Approve", "success"), ("reject", "Reject", "outline-danger")]
            rows.append(
                management_row(
                    record,
                    [
                        f"#{record.pk}",
                        record.patient_name or record.user.get_full_name() or record.user.username,
                        record.doctor_name or "Not provided",
                        record.created_at.strftime("%d %b %Y"),
                    ],
                    record.get_status_display(),
                    record.status,
                    actions,
                    edit_url=reverse("prescriptions:prescription_review", args=[record.pk]),
                    view_url=reverse("core:prescription_file", args=[record.pk]),
                )
            )
        elif section == "dispensing":
            rows.append(management_row(record, [record.order_item.order.order_number, record.pharmacist.get_full_name() or record.pharmacist.username, record.batch.batch_number, str(record.quantity)], "Recorded", "active", edit_url=reverse("dashboards:management_edit", args=["dispensing", record.pk])))
        elif section == "quality_complaints":
            rows.append(management_row(record, [record.product.name, record.user.get_full_name() or record.user.username, record.batch_number or "Not supplied", record.created_at.strftime("%d %b %Y")], record.get_status_display(), record.status, edit_url=reverse("dashboards:management_edit", args=["quality_complaints", record.pk])))
        elif section == "coupons":
            discount = f"{record.discount_value}%" if record.discount_type == Coupon.DiscountType.PERCENTAGE else f"₹{record.discount_value}"
            rows.append(management_row(record, [record.code, discount, f"₹{record.minimum_order}", f"{record.start_date:%d %b} - {record.end_date:%d %b %Y}"], "Active" if record.is_active else "Inactive", "active" if record.is_active else "inactive", [("deactivate" if record.is_active else "activate", "Deactivate" if record.is_active else "Activate", "outline-danger" if record.is_active else "success")], reverse("dashboards:management_edit", args=["coupons", record.pk])))
        elif section == "doctors":
            rows.append(management_row(record, [record.full_name, record.specialization, f"{record.experience_years} years", record.clinic_name or "Not provided"], "Verified" if record.is_verified else "Pending", "active" if record.is_verified else "pending", [("unverify" if record.is_verified else "verify", "Remove verification" if record.is_verified else "Verify", "outline-danger" if record.is_verified else "success")], edit_url=reverse("dashboards:management_edit", args=["doctors", record.pk]), view_url=reverse("core:doctor_credential", args=[record.pk]) if record.qualification_document else ""))
        elif section == "pharmacists":
            rows.append(management_row(record, [record.full_name, record.registration_number, record.pharmacy_name, record.state], "Verified" if record.is_verified else "Pending", "active" if record.is_verified else "pending", [("unverify" if record.is_verified else "verify", "Remove verification" if record.is_verified else "Verify", "outline-danger" if record.is_verified else "success")], edit_url=reverse("dashboards:management_edit", args=["pharmacists", record.pk])))
        elif section == "blog":
            rows.append(management_row(record, [record.title, record.category.name if record.category else "Uncategorised", record.author.get_full_name() if record.author else "MediMart editorial", record.updated_at.strftime("%d %b %Y")], record.get_status_display(), record.status, [("draft" if record.status == BlogPost.Status.PUBLISHED else "publish", "Move to draft" if record.status == BlogPost.Status.PUBLISHED else "Publish", "outline-secondary" if record.status == BlogPost.Status.PUBLISHED else "success")], reverse("dashboards:management_edit", args=["blog", record.pk])))
        elif section == "blog_categories":
            rows.append(management_row(record, [record.name, str(record.post_count), record.description[:100] or "No description", record.slug], "Available", "active", edit_url=reverse("dashboards:management_edit", args=["blog_categories", record.pk])))
        elif section == "notifications":
            rows.append(management_row(record, [record.title, record.user.get_full_name() or record.user.username, record.get_notification_type_display(), record.created_at.strftime("%d %b %Y, %H:%M")], "Read" if record.is_read else "Unread", "active" if record.is_read else "pending", [("unread" if record.is_read else "read", "Mark unread" if record.is_read else "Mark read", "outline-secondary")], edit_url=reverse("dashboards:management_edit", args=["notifications", record.pk])))
        elif section == "notification_deliveries":
            actions = [("retry", "Retry", "outline-success")] if record.status == NotificationDelivery.Status.FAILED else []
            rows.append(management_row(record, [record.notification.title, record.destination, str(record.attempts), record.next_attempt_at.strftime("%d %b %Y, %H:%M")], record.get_status_display(), record.status, actions))
        elif section == "payments":
            rows.append(management_row(record, [record.order.order_number, record.order.customer.get_full_name() or record.order.customer.username, f"₹{record.amount}", record.gateway_payment_id or record.gateway_order_id or "Not assigned"], record.get_status_display(), record.status, edit_url=reverse("dashboards:management_edit", args=["payments", record.pk])))
        elif section == "refunds":
            actions = [("retry", "Retry", "outline-success")] if record.status == Refund.Status.FAILED else []
            rows.append(management_row(record, [record.payment.order.order_number, f"₹{record.amount}", record.reason, record.gateway_refund_id or "Not assigned"], record.get_status_display(), record.status, actions, edit_url=reverse("dashboards:management_edit", args=["refunds", record.pk])))
        elif section == "warehouses":
            rows.append(management_row(record, [record.code, record.name, record.pincode, record.address[:100]], "Active" if record.is_active else "Inactive", "active" if record.is_active else "inactive", [("deactivate" if record.is_active else "activate", "Deactivate" if record.is_active else "Activate", "outline-danger" if record.is_active else "success")], reverse("dashboards:management_edit", args=["warehouses", record.pk])))
        elif section == "inventory":
            available = max(0, record.quantity - record.reserved_quantity)
            rows.append(management_row(record, [f"{record.vendor_product.product.name} · {record.batch_number}", record.warehouse.name, f"{available} available / {record.quantity} total", record.expires_on.strftime("%d %b %Y") if record.expires_on else "Not set"], "Available" if available else "Depleted", "active" if available else "inactive", edit_url=reverse("dashboards:management_edit", args=["inventory", record.pk])))
        elif section == "temperature_logs":
            rows.append(management_row(record, [record.batch.batch_number, f"{record.temperature_celsius} °C", record.recorded_at.strftime("%d %b %Y, %H:%M"), record.source], "Excursion" if record.is_excursion else "Within range", "inactive" if record.is_excursion else "active", edit_url=reverse("dashboards:management_edit", args=["temperature_logs", record.pk])))
        elif section == "recalls":
            recall_actions = []
            if record.status == RecallNotice.Status.DRAFT:
                recall_actions.append(("activate", "Activate", "outline-danger"))
            elif record.status == RecallNotice.Status.ACTIVE:
                recall_actions.append(("complete", "Complete", "success"))
            rows.append(management_row(record, [record.reference, record.product.name, record.batch.batch_number if record.batch else "All batches", record.created_at.strftime("%d %b %Y")], record.get_status_display(), record.status, recall_actions, edit_url=reverse("dashboards:management_edit", args=["recalls", record.pk])))
        elif section == "shipments":
            rows.append(management_row(record, [record.order.order_number, record.courier_name or "Not assigned", record.tracking_number or "Not assigned", record.promised_at.strftime("%d %b %Y, %H:%M") if record.promised_at else "Not set"], record.get_status_display(), record.status, edit_url=reverse("dashboards:management_edit", args=["shipments", record.pk])))
        elif section == "returns":
            actions = []
            if record.status == ReturnRequest.Status.REQUESTED:
                actions.append(("review", "Start review", "outline-primary"))
            elif record.status == ReturnRequest.Status.UNDER_REVIEW:
                actions.extend([("approve", "Approve", "success"), ("reject", "Reject", "outline-danger")])
            elif record.status == ReturnRequest.Status.APPROVED:
                actions.append(("pickup", "Schedule pickup", "outline-success"))
            elif record.status == ReturnRequest.Status.PICKUP_SCHEDULED:
                actions.append(("received", "Mark received", "outline-primary"))
            elif record.status == ReturnRequest.Status.RECEIVED:
                if record.inspection_decision == ReturnRequest.InspectionDecision.PENDING:
                    actions.append(("inspect_accept", "Accept inspection", "success"))
                    if record.order_item.dispensed_batch_id:
                        actions.append(("inspect_restock", "Accept & restock", "outline-success"))
                    actions.extend([
                        ("inspect_quarantine", "Quarantine", "outline-warning"),
                        ("inspect_reject", "Reject after inspection", "outline-danger"),
                    ])
                elif record.inspection_decision in {
                    ReturnRequest.InspectionDecision.ACCEPTED,
                    ReturnRequest.InspectionDecision.RESTOCKED,
                }:
                    actions.append(("refund", "Queue refund", "success"))
            elif record.status == ReturnRequest.Status.REFUND_PENDING and _linked_return_refund(record) and _linked_return_refund(record).status == Refund.Status.COMPLETED:
                actions.append(("complete", "Complete return", "success"))
            rows.append(management_row(record, [record.order_item.order.order_number, record.user.get_full_name() or record.user.username, f"{record.order_item.product_name} · {record.quantity} unit(s)", record.get_reason_display()], record.get_status_display(), record.status, actions, edit_url=reverse("dashboards:management_edit", args=["returns", record.pk])))
        elif section == "lab_tests":
            rows.append(management_row(record, [record.name, record.partner.name, f"₹{record.price} / ₹{record.mrp}", "Home collection" if record.is_home_collection else "Partner centre"], "Active" if record.is_active else "Inactive", "active" if record.is_active else "inactive", edit_url=reverse("dashboards:management_edit", args=["lab_tests", record.pk])))
        elif section == "lab_partners":
            rows.append(management_row(record, [record.name, record.city, record.accreditations or "Not supplied", record.phone or "Not supplied"], "Active" if record.is_active else "Inactive", "active" if record.is_active else "inactive", [("deactivate" if record.is_active else "activate", "Deactivate" if record.is_active else "Activate", "outline-danger" if record.is_active else "success")], edit_url=reverse("dashboards:management_edit", args=["lab_partners", record.pk])))
        elif section == "lab_bookings":
            lab_actions = {
                "requested": [("confirm", "Confirm", "success"), ("cancel", "Cancel", "outline-danger")],
                "confirmed": [("sample_collected", "Sample collected", "outline-primary"), ("cancel", "Cancel", "outline-danger")],
                "sample_collected": [("processing", "Mark processing", "outline-primary")],
                "processing": [("report_ready", "Report ready", "success"), ("recollection", "Request recollection", "outline-warning")],
                "recollection": [("confirmed", "Reschedule collection", "outline-primary"), ("cancel", "Cancel", "outline-danger")],
            }.get(record.status, [])
            rows.append(management_row(record, [f"#{record.pk}", record.user.get_full_name() or record.user.username, record.lab_test.name, record.scheduled_start.strftime("%d %b %Y, %H:%M") if record.scheduled_start else "Slot pending"], record.get_status_display(), record.status, lab_actions, edit_url=reverse("dashboards:management_edit", args=["lab_bookings", record.pk])))
        elif section == "lab_slots":
            rows.append(management_row(record, [record.partner.name, record.starts_at.strftime("%d %b %Y, %H:%M"), record.ends_at.strftime("%d %b %Y, %H:%M"), f"{record.booked_count} / {record.capacity}"], "Blackout" if record.is_blackout else ("Available" if record.available_capacity else "Full"), "inactive" if record.is_blackout or not record.available_capacity else "active", edit_url=reverse("dashboards:management_edit", args=["lab_slots", record.pk])))
        elif section == "consultations":
            consultation_actions = {
                "requested": [("confirm", "Confirm", "success"), ("cancel", "Cancel", "outline-danger")],
                "confirmed": [("in_progress", "Start", "outline-primary"), ("cancel", "Cancel", "outline-danger")],
                "in_progress": [("complete", "Complete", "success")],
            }.get(record.status, [])
            rows.append(management_row(record, [record.user.get_full_name() or record.user.username, f"Dr. {record.doctor.full_name}", record.get_mode_display(), record.scheduled_at.strftime("%d %b %Y, %H:%M") if record.scheduled_at else "Schedule pending"], record.get_status_display(), record.status, consultation_actions, edit_url=reverse("dashboards:management_edit", args=["consultations", record.pk]), view_url=reverse("healthcare:consultation_detail", args=[record.pk]) if record.status != Consultation.Status.CANCELLED else ""))
        elif section == "audit":
            rows.append(management_row(record, [record.action, record.actor.get_full_name() or record.actor.username if record.actor else "System", f"{record.target_type} #{record.target_id}".strip(), record.summary or "No summary"], "Recorded", "active"))

    if section in MANAGEMENT_FORMS:
        for row in rows:
            if not (section == "users" and row["pk"] == request.user.pk):
                row["delete_url"] = reverse("dashboards:management_record_action", args=[section, row["pk"]])
    return render(request, "dashboards/management_records.html", {"section": section, "title": title, "description": description, "columns": columns, "rows": rows, "query": query, "page_obj": page_obj, "create_url": create_url, "create_label": create_label})


@role_required(*OPERATIONS_ROLES, allow_staff=True)
@require_POST
def management_record_action(request, section, pk):
    if not management_section_allowed(request.user, section):
        raise PermissionDenied
    action = request.POST.get("action")
    if action == "delete":
        if section not in MANAGEMENT_FORMS:
            raise PermissionDenied
        model = MANAGEMENT_FORMS[section][0]
        record = get_object_or_404(model, pk=pk)
        if section == "users" and (record == request.user or (record.is_superuser and not request.user.is_superuser)):
            raise PermissionDenied
        label = str(record)
        try:
            record.delete()
        except (ProtectedError, IntegrityError):
            messages.error(request, "This record is referenced by other records and cannot be deleted. Deactivate it instead.")
            return redirect("dashboards:management_records", section=section)
        record_audit(request, f"management.{section}.delete", record, f"Deleted {label} from the Operations Center.")
        messages.success(request, f"{label} deleted successfully.")
        return redirect("dashboards:management_records", section=section)
    if section == "users":
        record = get_object_or_404(User, pk=pk)
        if record == request.user or (record.is_superuser and not request.user.is_superuser):
            raise PermissionDenied
        record.is_active = action == "activate"
        record.save(update_fields=["is_active"])
    elif section == "products":
        record = get_object_or_404(Product, pk=pk)
        if action in {"activate", "deactivate"}:
            record.is_active = action == "activate"
            record.save(update_fields=["is_active", "updated_at"])
        elif action in {"feature", "unfeature"}:
            record.is_featured = action == "feature"
            record.save(update_fields=["is_featured", "updated_at"])
    elif section in {"categories", "brands", "coupons"}:
        model = {"categories": Category, "brands": Brand, "coupons": Coupon}[section]
        record = get_object_or_404(model, pk=pk)
        record.is_active = action == "activate"
        record.save(update_fields=["is_active", "updated_at"])
    elif section == "vendors":
        record = get_object_or_404(Vendor, pk=pk)
        if action == "activate" and record.requires_regulatory_license and not record.has_verified_license:
            messages.error(request, "A compatible business licence must be verified before activation.")
            return redirect("dashboards:management_records", section=section)
        record.is_active = action == "activate"
        record.is_approved = action == "activate"
        record.save(update_fields=["is_active", "is_approved", "updated_at"])
        if action != "activate":
            record.vendor_products.update(is_active=False)
    elif section == "offers":
        record = get_object_or_404(VendorProduct.objects.select_related("product", "vendor"), pk=pk)
        if action == "activate" and record.product.requires_business_license:
            valid_licenses = record.vendor.licenses.filter(status=BusinessLicense.Status.VERIFIED)
            if not any(item.is_compatible_with(record.product.required_license_type) for item in valid_licenses):
                messages.error(request, "A compatible verified seller licence is required before publication.")
                return redirect("dashboards:management_records", section=section)
        record.is_active = action == "activate"
        record.is_approved = action == "activate"
        record.save(update_fields=["is_active", "is_approved", "updated_at"])
    elif section == "prescriptions":
        record = get_object_or_404(Prescription, pk=pk)
        if action == "approve":
            if not record.valid_until or record.valid_until < timezone.localdate() or not record.items.exists():
                messages.error(request, "Add a current validity date and at least one prescribed product before approval.")
                return redirect("dashboards:management_records", section=section)
            record.mark_approved(request.user)
        elif action == "reject":
            record.mark_rejected(request.user, request.POST.get("reason", "Rejected during clinical review."))
    elif section == "doctors":
        record = get_object_or_404(DoctorProfile, pk=pk)
        if action == "verify" and not all(
            [record.registration_number, record.medical_council, record.qualification, record.qualification_document]
        ):
            messages.error(request, "Registration, council, qualification, and credential document are required.")
            return redirect("dashboards:management_records", section=section)
        record.is_verified = action == "verify"
        record.verified_by = request.user if record.is_verified else None
        record.verified_at = timezone.now() if record.is_verified else None
        record.save(update_fields=["is_verified", "verified_by", "verified_at", "updated_at"])
    elif section == "pharmacists":
        record = get_object_or_404(PharmacistProfile, pk=pk)
        if action == "verify" and not all([record.registration_number, record.pharmacy_license_number, record.credential_document]):
            messages.error(request, "Registration, pharmacy licence, and credential document are required.")
            return redirect("dashboards:management_records", section=section)
        record.is_verified = action == "verify"
        record.verified_by = request.user if record.is_verified else None
        record.verified_at = timezone.now() if record.is_verified else None
        record.save(update_fields=["is_verified", "verified_by", "verified_at", "updated_at"])
    elif section == "recalls":
        record = get_object_or_404(RecallNotice, pk=pk)
        if action == "activate":
            activate_recall_notice(record, actor=request.user)
        elif action == "complete":
            record.status = RecallNotice.Status.COMPLETED
            record.save(update_fields=["status", "updated_at"])
        else:
            raise PermissionDenied
    elif section == "blog":
        record = get_object_or_404(BlogPost, pk=pk)
        record.status = BlogPost.Status.PUBLISHED if action == "publish" else BlogPost.Status.DRAFT
        record.save(update_fields=["status", "published_at", "updated_at"])
    elif section == "notifications":
        record = get_object_or_404(Notification, pk=pk)
        record.is_read = action == "read"
        record.save(update_fields=["is_read"])
    elif section == "notification_deliveries":
        record = get_object_or_404(NotificationDelivery, pk=pk, channel=NotificationDelivery.Channel.EMAIL)
        if action != "retry" or record.status != NotificationDelivery.Status.FAILED:
            raise PermissionDenied
        record.status = NotificationDelivery.Status.PENDING
        record.next_attempt_at = timezone.now()
        record.last_error = ""
        record.save(update_fields=["status", "next_attempt_at", "last_error", "updated_at"])
    elif section == "refunds":
        record = get_object_or_404(Refund, pk=pk)
        if action != "retry" or record.status != Refund.Status.FAILED:
            raise PermissionDenied
        record.status = Refund.Status.REQUESTED
        record.save(update_fields=["status", "updated_at"])
    elif section == "warehouses":
        record = get_object_or_404(Warehouse, pk=pk)
        record.is_active = action == "activate"
        record.save(update_fields=["is_active"])
    elif section == "lab_partners":
        record = get_object_or_404(LabPartner, pk=pk)
        if action not in {"activate", "deactivate"}:
            raise PermissionDenied
        record.is_active = action == "activate"
        record.save(update_fields=["is_active"])
    elif section == "returns":
        record = get_object_or_404(
            ReturnRequest.objects.select_related("order_item__order__payment", "user", "refund"),
            pk=pk,
        )
        allowed = {
            ReturnRequest.Status.REQUESTED: {"review": ReturnRequest.Status.UNDER_REVIEW},
            ReturnRequest.Status.UNDER_REVIEW: {
                "approve": ReturnRequest.Status.APPROVED,
                "reject": ReturnRequest.Status.REJECTED,
            },
            ReturnRequest.Status.APPROVED: {"pickup": ReturnRequest.Status.PICKUP_SCHEDULED},
            ReturnRequest.Status.PICKUP_SCHEDULED: {"received": ReturnRequest.Status.RECEIVED},
            ReturnRequest.Status.RECEIVED: {
                "inspect_accept": ReturnRequest.Status.RECEIVED,
                "inspect_restock": ReturnRequest.Status.RECEIVED,
                "inspect_quarantine": ReturnRequest.Status.RECEIVED,
                "inspect_reject": ReturnRequest.Status.REJECTED,
                "refund": ReturnRequest.Status.REFUND_PENDING,
            },
            ReturnRequest.Status.REFUND_PENDING: {"complete": ReturnRequest.Status.COMPLETED},
        }
        next_status = allowed.get(record.status, {}).get(action)
        if not next_status:
            raise PermissionDenied

        with transaction.atomic():
            if action == "refund":
                try:
                    create_return_refund(record, requested_by=request.user)
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect("dashboards:management_records", section=section)
            else:
                record.status = next_status
                update_fields = ["status", "updated_at"]
                if action in {"approve", "reject"}:
                    record.reviewed_by = request.user
                    update_fields.append("reviewed_by")
                if action == "approve":
                    record.approved_at = timezone.now()
                    update_fields.append("approved_at")
                if action == "reject":
                    record.resolution_note = request.POST.get("reason", "Return rejected during review.").strip()[:500]
                    update_fields.append("resolution_note")
                if action == "pickup":
                    record.pickup_scheduled_at = timezone.now()
                    record.pickup_reference = request.POST.get("pickup_reference", "").strip()[:120]
                    update_fields.extend(["pickup_scheduled_at", "pickup_reference"])
                if action == "received":
                    record.received_at = timezone.now()
                    update_fields.append("received_at")
                if action in {"inspect_accept", "inspect_restock", "inspect_quarantine", "inspect_reject"}:
                    decision = {
                        "inspect_accept": ReturnRequest.InspectionDecision.ACCEPTED,
                        "inspect_restock": ReturnRequest.InspectionDecision.RESTOCKED,
                        "inspect_quarantine": ReturnRequest.InspectionDecision.QUARANTINED,
                        "inspect_reject": ReturnRequest.InspectionDecision.REJECTED,
                    }[action]
                    record.inspection_decision = decision
                    record.inspected_by = request.user
                    record.inspected_at = timezone.now()
                    if decision in {ReturnRequest.InspectionDecision.QUARANTINED, ReturnRequest.InspectionDecision.REJECTED}:
                        record.resolution_note = request.POST.get("reason", "Return failed inspection.").strip()[:500]
                        update_fields.append("resolution_note")
                    elif decision == ReturnRequest.InspectionDecision.RESTOCKED:
                        restock_return_inventory(record, actor=request.user)
                        record.resolution_note = "Accepted after inspection and returned to traced stock where batch data was available."
                        update_fields.append("resolution_note")
                    update_fields.extend(["inspection_decision", "inspected_by", "inspected_at"])
                if action == "complete":
                    try:
                        linked_refund = record.refund
                    except Refund.DoesNotExist:
                        linked_refund = None
                    if not linked_refund or linked_refund.status != Refund.Status.COMPLETED:
                        messages.error(request, "Complete the linked refund before closing this return.")
                        return redirect("dashboards:management_records", section=section)
                record.save(update_fields=update_fields)

        if action != "refund":
            create_notification(
                record.user,
                "Return request updated",
                f"Your return request for {record.order_item.product_name} is now {record.get_status_display().lower()}.",
                Notification.NotificationType.ORDER,
                reverse("orders:return_list"),
            )
    elif section == "lab_bookings":
        record = get_object_or_404(LabBooking, pk=pk)
        transitions = {
            "confirm": (LabBooking.Status.CONFIRMED, {}),
            "sample_collected": (LabBooking.Status.SAMPLE_COLLECTED, {}),
            "processing": (LabBooking.Status.PROCESSING, {}),
            "report_ready": (LabBooking.Status.REPORT_READY, {"report_ready_at": timezone.now()}),
            "recollection": (LabBooking.Status.RECOLLECTION, {}),
            "cancel": (LabBooking.Status.CANCELLED, {}),
        }
        if action not in transitions:
            raise PermissionDenied
        next_status, extra = transitions[action]
        allowed = {
            LabBooking.Status.REQUESTED: {LabBooking.Status.CONFIRMED, LabBooking.Status.CANCELLED},
            LabBooking.Status.CONFIRMED: {LabBooking.Status.SAMPLE_COLLECTED, LabBooking.Status.CANCELLED},
            LabBooking.Status.SAMPLE_COLLECTED: {LabBooking.Status.PROCESSING},
            LabBooking.Status.PROCESSING: {LabBooking.Status.REPORT_READY, LabBooking.Status.RECOLLECTION},
            LabBooking.Status.RECOLLECTION: {LabBooking.Status.CONFIRMED, LabBooking.Status.CANCELLED},
        }
        if next_status not in allowed.get(record.status, set()):
            raise PermissionDenied
        record.status = next_status
        for field, value in extra.items():
            setattr(record, field, value)
        record.save(update_fields=["status", *extra.keys(), "updated_at"])
        create_notification(
            record.user,
            "Lab booking updated",
            f"Your lab booking for {record.lab_test.name} is now {record.get_status_display().lower()}.",
            Notification.NotificationType.GENERAL,
            reverse("healthcare:lab_bookings"),
        )
    elif section == "consultations":
        record = get_object_or_404(Consultation, pk=pk)
        transitions = {
            "confirm": Consultation.Status.CONFIRMED,
            "in_progress": Consultation.Status.IN_PROGRESS,
            "complete": Consultation.Status.COMPLETED,
            "cancel": Consultation.Status.CANCELLED,
        }
        next_status = transitions.get(action)
        allowed = {
            Consultation.Status.REQUESTED: {Consultation.Status.CONFIRMED, Consultation.Status.CANCELLED},
            Consultation.Status.CONFIRMED: {Consultation.Status.IN_PROGRESS, Consultation.Status.CANCELLED},
            Consultation.Status.IN_PROGRESS: {Consultation.Status.COMPLETED},
        }
        if next_status not in allowed.get(record.status, set()):
            raise PermissionDenied
        record.status = next_status
        record.save(update_fields=["status", "updated_at"])
        create_notification(
            record.user,
            "Consultation updated",
            f"Your consultation is now {record.get_status_display().lower()}.",
            Notification.NotificationType.GENERAL,
            reverse("healthcare:consultation_detail", args=[record.pk]),
        )
    else:
        raise PermissionDenied
    record_audit(request, f"management.{section}.{action}", record, "Management record updated.")
    messages.success(request, "Record updated successfully.")
    return redirect("dashboards:management_records", section=section)


MANAGEMENT_FORMS = {
    "users": (User, UserManagementForm, "User account"),
    "products": (Product, ProductManagementForm, "Product"),
    "categories": (Category, CategoryManagementForm, "Category"),
    "brands": (Brand, BrandManagementForm, "Brand"),
    "coupons": (Coupon, CouponManagementForm, "Coupon"),
    "blog": (BlogPost, BlogManagementForm, "Health guide"),
    "blog_categories": (BlogCategory, BlogCategoryManagementForm, "Guide category"),
    "warehouses": (Warehouse, WarehouseManagementForm, "Warehouse"),
    "inventory": (InventoryBatch, InventoryBatchManagementForm, "Inventory batch"),
    "shipments": (Shipment, ShipmentManagementForm, "Shipment"),
    "lab_tests": (LabTest, LabTestManagementForm, "Lab test"),
    "lab_partners": (LabPartner, LabPartnerManagementForm, "Lab partner"),
    "vendors": (Vendor, VendorManagementForm, "Seller"),
    "offers": (VendorProduct, VendorProductManagementForm, "Seller offer"),
    "licenses": (BusinessLicense, BusinessLicenseManagementForm, "Business licence"),
    "doctors": (DoctorProfile, DoctorManagementForm, "Doctor profile"),
    "pharmacists": (PharmacistProfile, PharmacistProfileManagementForm, "Pharmacist profile"),
    "notifications": (Notification, NotificationManagementForm, "Notification"),
    "orders": (Order, OrderManagementForm, "Order"),
    "payments": (Payment, PaymentManagementForm, "Payment"),
    "refunds": (Refund, RefundManagementForm, "Refund"),
    "returns": (ReturnRequest, ReturnRequestManagementForm, "Return request"),
    "lab_bookings": (LabBooking, LabBookingManagementForm, "Lab booking"),
    "lab_slots": (LabCollectionSlot, LabCollectionSlotManagementForm, "Lab collection slot"),
    "consultations": (Consultation, ConsultationManagementForm, "Consultation"),
    "temperature_logs": (InventoryTemperatureLog, InventoryTemperatureLogManagementForm, "Temperature log"),
    "recalls": (RecallNotice, RecallNoticeManagementForm, "Recall notice"),
    "dispensing": (DispensingRecord, DispensingRecordManagementForm, "Dispensing record"),
    "quality_complaints": (QualityComplaint, QualityComplaintManagementForm, "Quality complaint"),
}


@role_required(*OPERATIONS_ROLES, allow_staff=True)
def management_form(request, section, pk=None):
    if section not in MANAGEMENT_FORMS or not management_section_allowed(request.user, section):
        raise PermissionDenied
    model, form_class, label = MANAGEMENT_FORMS[section]
    instance = get_object_or_404(model, pk=pk) if pk else None
    if section == "users" and instance and instance.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    if (
        section == "users"
        and instance
        and getattr(getattr(instance, "profile", None), "role", None) == UserProfile.Role.ADMIN
        and not request.user.is_superuser
    ):
        raise PermissionDenied
    if request.method == "POST":
        form_kwargs = {"actor": request.user} if section == "users" else {}
        form = form_class(request.POST, request.FILES, instance=instance, **form_kwargs)
        if form.is_valid():
            if section == "users":
                record = form.save()
            else:
                record = form.save(commit=False)
                if section == "blog" and not record.author_id:
                    record.author = request.user
                if section == "recalls" and not record.initiated_by_id:
                    record.initiated_by = request.user
                if section == "pharmacists":
                    record.verified_by = request.user if record.is_verified else None
                    record.verified_at = timezone.now() if record.is_verified else None
                if section == "quality_complaints" and record.status in {
                    QualityComplaint.Status.UNDER_REVIEW,
                    QualityComplaint.Status.ESCALATED,
                    QualityComplaint.Status.RESOLVED,
                    QualityComplaint.Status.CLOSED,
                }:
                    record.reviewed_by = request.user
                record.save()
                form.save_m2m()
                if section == "licenses" and record.status in {
                    BusinessLicense.Status.VERIFIED,
                    BusinessLicense.Status.REJECTED,
                }:
                    record.reviewed_by = request.user
                    record.reviewed_at = timezone.now()
                    record.save(update_fields=["reviewed_by", "reviewed_at", "updated_at"])
                elif section == "doctors":
                    record.verified_by = request.user if record.is_verified else None
                    record.verified_at = timezone.now() if record.is_verified else None
                    record.save(update_fields=["verified_by", "verified_at", "updated_at"])
                elif section == "pharmacists":
                    record.save(update_fields=["verified_by", "verified_at", "updated_at"])
                elif section == "temperature_logs":
                    batch = record.batch
                    lower, upper = batch.storage_min_celsius, batch.storage_max_celsius
                    outside_range = (lower is not None and record.temperature_celsius < lower) or (upper is not None and record.temperature_celsius > upper)
                    if outside_range or record.is_excursion:
                        batch.excursion_status = "excursion"
                        batch.is_quarantined = True
                        batch.quarantine_reason = "Temperature excursion requires investigation."
                        batch.save(update_fields=["excursion_status", "is_quarantined", "quarantine_reason", "updated_at"])
                elif section == "quality_complaints":
                    record.save(update_fields=["reviewed_by", "updated_at"])
                elif section == "orders" and record.order_status == Order.OrderStatus.DELIVERED:
                    try:
                        finalize_order_inventory_sale(record.pk, actor=request.user)
                    except CheckoutStockError as exc:
                        messages.error(request, str(exc))
                        return redirect("dashboards:management_records", section=section)
            record_audit(
                request,
                f"management.{section}.{'updated' if instance else 'created'}",
                record,
                f"{label} saved from the Operations Center.",
            )
            messages.success(request, f"{label} saved successfully.")
            return redirect("dashboards:management_records", section=section)
    else:
        form_kwargs = {"actor": request.user} if section == "users" else {}
        form = form_class(instance=instance, **form_kwargs)
    return render(request, "dashboards/management_form.html", {"form": form, "section": section, "label": label, "is_edit": bool(instance)})


def _render_admin_dashboard(request, today, monthly_orders):
    todays_orders = Order.objects.filter(created_at__date=today)
    paid_orders = Order.objects.filter(payment_status=Order.PaymentStatus.PAID)

    stats = {
        "total_customers": UserProfile.objects.filter(role=UserProfile.Role.CUSTOMER).count(),
        "total_manufacturers": UserProfile.objects.filter(
            role=UserProfile.Role.MANUFACTURER
        ).count(),
        "total_doctors": UserProfile.objects.filter(role=UserProfile.Role.DOCTOR).count(),
        "total_delivery_staff": UserProfile.objects.filter(
            role=UserProfile.Role.DELIVERY_STAFF
        ).count(),
        "total_vendors": Vendor.objects.count(),
        "total_products": Product.objects.count(),
        "total_orders": Order.objects.count(),
        "pending_orders": Order.objects.filter(order_status=Order.OrderStatus.PENDING).count(),
        "todays_orders": todays_orders.count(),
        "todays_revenue": paid_orders.filter(created_at__date=today).aggregate(
            total=Sum("total_amount")
        )["total"]
        or 0,
        "monthly_revenue": paid_orders.filter(
            created_at__year=today.year,
            created_at__month=today.month,
        ).aggregate(total=Sum("total_amount"))["total"]
        or 0,
        "monthly_orders": monthly_orders.count(),
        "pending_prescriptions": Prescription.objects.filter(
            status=Prescription.Status.PENDING
        ).count(),
        "pending_vendor_approvals": Vendor.objects.filter(is_approved=False).count(),
        "pending_license_reviews": BusinessLicense.objects.exclude(
            status__in=[BusinessLicense.Status.VERIFIED, BusinessLicense.Status.REJECTED]
        ).count(),
        "pending_offer_approvals": VendorProduct.objects.filter(
            Q(is_approved=False) | Q(product__is_active=False)
        ).count(),
        "low_stock_products": VendorProduct.objects.filter(
            stock_quantity__lte=5,
            is_active=True,
            is_approved=True,
        ).count(),
        "open_support_tickets": SupportTicket.objects.exclude(
            status=SupportTicket.Status.CLOSED
        ).count(),
    }

    recent_orders = Order.objects.select_related("customer", "delivery_staff").all()[:8]
    pending_prescriptions = Prescription.objects.select_related("user").filter(
        status=Prescription.Status.PENDING
    )[:8]
    pending_vendors = Vendor.objects.filter(is_approved=False)[:8]
    pending_licenses = (
        BusinessLicense.objects.exclude(
            status__in=[BusinessLicense.Status.VERIFIED, BusinessLicense.Status.REJECTED]
        )
        .select_related("vendor", "reviewed_by")[:12]
    )
    pending_offers = (
        VendorProduct.objects.filter(Q(is_approved=False) | Q(product__is_active=False))
        .select_related("vendor", "product")[:8]
    )
    low_stock_products = (
        VendorProduct.objects.filter(stock_quantity__lte=5, is_active=True, is_approved=True)
        .select_related("vendor", "product")[:8]
    )
    delivery_staff = User.objects.filter(profile__role=UserProfile.Role.DELIVERY_STAFF).order_by(
        "username"
    )
    recent_support_tickets = SupportTicket.objects.select_related("user").exclude(
        status=SupportTicket.Status.CLOSED
    )[:8]
    management_sections = [
        ("Users", "users", "people"),
        ("Products", "products", "box-seam"),
        ("Categories", "categories", "diagram-3"),
        ("Brands", "brands", "award"),
        ("Sellers", "vendors", "shop"),
        ("Business Licences", "licenses", "patch-check"),
        ("Seller Offers", "offers", "tags"),
        ("Orders", "orders", "bag-check"),
        ("Prescriptions", "prescriptions", "file-earmark-medical"),
        ("Coupons", "coupons", "ticket-perforated"),
        ("Doctors", "doctors", "person-vcard"),
        ("Pharmacists", "pharmacists", "person-badge"),
        ("Dispensing Records", "dispensing", "capsule"),
        ("Quality Complaints", "quality_complaints", "exclamation-triangle"),
        ("Health Guides", "blog", "journal-medical"),
        ("Guide Categories", "blog_categories", "collection"),
        ("Support", "support", "headset"),
        ("Notifications", "notifications", "bell"),
        ("Email Delivery", "notification_deliveries", "send-check"),
        ("Payments", "payments", "credit-card"),
        ("Refunds", "refunds", "arrow-counterclockwise"),
        ("Warehouses", "warehouses", "building"),
        ("Inventory Batches", "inventory", "boxes"),
        ("Temperature Logs", "temperature_logs", "thermometer-half"),
        ("Product Recalls", "recalls", "shield-exclamation"),
        ("Shipments", "shipments", "truck"),
        ("Returns & Refunds", "returns", "arrow-return-left"),
        ("Lab Tests", "lab_tests", "eyedropper"),
        ("Lab Partners", "lab_partners", "hospital"),
        ("Lab Bookings", "lab_bookings", "calendar2-week"),
        ("Lab Collection Slots", "lab_slots", "clock-history"),
        ("Consultations", "consultations", "camera-video"),
        ("Audit Trail", "audit", "activity"),
    ]
    admin_links = [
        (label, reverse("dashboards:management_records", args=[section]), icon)
        for label, section, icon in management_sections
        if management_section_allowed(request.user, section)
    ]

    return render(
        request,
        "dashboards/admin_dashboard.html",
        {
            "stats": stats,
            "recent_orders": recent_orders,
            "pending_prescriptions": pending_prescriptions,
            "pending_vendors": pending_vendors,
            "pending_licenses": pending_licenses,
            "pending_offers": pending_offers,
            "low_stock_products": low_stock_products,
            "delivery_staff": delivery_staff,
            "recent_support_tickets": recent_support_tickets,
            "admin_links": admin_links,
            "can_view_financials": has_capability(request.user, "finance.manage"),
            "can_review_licenses": has_capability(request.user, "compliance.review"),
            "can_manage_catalog": has_capability(request.user, "catalog.manage"),
            "can_manage_fulfillment": has_capability(request.user, "fulfillment.manage"),
            "can_manage_clinical": has_capability(request.user, "clinical.manage"),
            "can_manage_inventory": has_capability(request.user, "fulfillment.manage"),
            "can_manage_support": has_capability(request.user, "support.manage"),
        },
    )


def user_can_access_delivery_dashboard(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return has_capability(user, "dashboard.delivery")


@login_required
def delivery_dashboard(request):
    if not user_can_access_delivery_dashboard(request.user):
        messages.error(request, "Delivery dashboard access is limited to authorized delivery operations staff.")
        return redirect("accounts:dashboard")

    active_orders = Order.objects.filter(
        order_status__in=[
            Order.OrderStatus.CONFIRMED,
            Order.OrderStatus.PROCESSING,
            Order.OrderStatus.PACKED,
            Order.OrderStatus.SHIPPED,
            Order.OrderStatus.OUT_FOR_DELIVERY,
        ]
    ).select_related("customer", "address").prefetch_related("shipment").order_by("created_at")
    delivered_orders = Order.objects.filter(
        order_status=Order.OrderStatus.DELIVERED,
    ).select_related("shipment")
    if not request.user.is_superuser and getattr(request.user.profile, "role", None) == UserProfile.Role.DELIVERY_STAFF:
        active_orders = active_orders.filter(delivery_staff=request.user)
        delivered_orders = delivered_orders.filter(delivery_staff=request.user)

    stats = {
        "assigned_orders": active_orders.count(),
        "out_for_delivery": active_orders.filter(
            order_status=Order.OrderStatus.OUT_FOR_DELIVERY
        ).count(),
        "delivered_today": delivered_orders.filter(shipment__delivered_at__date=timezone.localdate()).count(),
        "total_delivered": delivered_orders.count(),
    }

    return render(
        request,
        "dashboards/delivery_dashboard.html",
        {
            "stats": stats,
            "active_orders": active_orders[:20],
        },
    )


@login_required
@require_POST
def update_delivery_order_status(request, pk):
    if not user_can_access_delivery_dashboard(request.user):
        messages.error(request, "Delivery dashboard access is limited to authorized delivery operations staff.")
        return redirect("accounts:dashboard")

    orders = Order.objects.all()
    if not request.user.is_superuser and getattr(request.user.profile, "role", None) == UserProfile.Role.DELIVERY_STAFF:
        orders = orders.filter(delivery_staff=request.user)
    order = get_object_or_404(orders, pk=pk)
    next_status = request.POST.get("status")
    allowed_transitions = {
        Order.OrderStatus.SHIPPED: {Order.OrderStatus.OUT_FOR_DELIVERY},
        Order.OrderStatus.OUT_FOR_DELIVERY: {Order.OrderStatus.DELIVERED},
    }
    if next_status not in allowed_transitions.get(order.order_status, set()):
        messages.error(request, "That delivery status transition is not allowed.")
        return redirect("dashboards:delivery_dashboard")

    if next_status == Order.OrderStatus.DELIVERED:
        shipment, _ = Shipment.objects.get_or_create(order=order)
        if not shipment.delivery_otp_verified_at:
            delivery_otp = request.POST.get("delivery_otp", "")
            if not shipment.verify_delivery_otp(delivery_otp):
                messages.error(request, "Enter the valid delivery OTP shared with the customer before completing delivery.")
                return redirect("dashboards:delivery_dashboard")
        proof = request.FILES.get("delivery_proof")
        recipient_name = " ".join(str(request.POST.get("recipient_name", "")).split())
        if proof:
            shipment.delivery_proof = proof
        if recipient_name:
            shipment.delivery_recipient_name = recipient_name
        shipment.status = Shipment.Status.DELIVERED
        shipment.delivered_at = timezone.now()
        shipment.save(update_fields=["status", "delivered_at", "delivery_proof", "delivery_recipient_name", "updated_at"])
        ShipmentEvent.objects.create(
            shipment=shipment,
            status=Shipment.Status.DELIVERED,
            description=f"Delivered by {request.user.get_full_name() or request.user.username}.",
        )
        try:
            finalize_order_inventory_sale(order.pk, actor=request.user)
        except CheckoutStockError as exc:
            messages.error(request, str(exc))
            return redirect("dashboards:delivery_dashboard")

    if next_status == Order.OrderStatus.OUT_FOR_DELIVERY:
        shipment, _ = Shipment.objects.get_or_create(order=order)
        delivery_otp = shipment.issue_delivery_otp()
        shipment.status = Shipment.Status.OUT_FOR_DELIVERY
        shipment.save(update_fields=["status", "updated_at"])
        ShipmentEvent.objects.create(
            shipment=shipment,
            status=Shipment.Status.OUT_FOR_DELIVERY,
            description=f"Out for delivery with {request.user.get_full_name() or request.user.username}.",
        )
        create_notification(
            order.customer,
            "Delivery verification code",
            f"Your MediMart delivery OTP for order {order.order_number} is {delivery_otp}. Share it only when your order arrives.",
            Notification.NotificationType.ORDER,
            order.get_absolute_url(),
        )

    order.order_status = next_status
    order.save(update_fields=["order_status", "updated_at"])
    OrderStatusHistory.objects.create(
        order=order,
        status=next_status,
        note=f"Updated from delivery dashboard by {request.user.username}.",
        actor=request.user,
    )
    record_audit(request, "delivery.status_changed", order, f"Order moved to {next_status}.")
    create_notification(
        order.customer,
        f"Order {order.get_order_status_display().lower()}",
        f"Your MediMart order {order.order_number} is now {order.get_order_status_display().lower()}.",
        Notification.NotificationType.ORDER,
        order.get_absolute_url(),
    )
    messages.success(request, f"Order {order.order_number} updated.")
    return redirect("dashboards:delivery_dashboard")


@role_required(UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.WAREHOUSE_MANAGER, allow_staff=True)
@require_POST
def assign_delivery_staff(request, pk):
    order = get_object_or_404(Order, pk=pk)
    staff_id = request.POST.get("delivery_staff")
    if staff_id:
        delivery_staff = get_object_or_404(
            User,
            pk=staff_id,
            profile__role=UserProfile.Role.DELIVERY_STAFF,
        )
        order.delivery_staff = delivery_staff
        message = f"Assigned {order.order_number} to {delivery_staff.username}."
    else:
        order.delivery_staff = None
        message = f"Removed delivery assignment from {order.order_number}."
    order.save(update_fields=["delivery_staff", "updated_at"])
    OrderStatusHistory.objects.create(
        order=order,
        status=order.order_status,
        note=f"Delivery assignment updated by {request.user.username}.",
        actor=request.user,
    )
    record_audit(
        request,
        "delivery.assignment_changed",
        order,
        message,
        {"delivery_staff_id": order.delivery_staff_id},
    )
    messages.success(request, message)
    return redirect("dashboards:admin_dashboard")


@role_required(UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.COMPLIANCE_OFFICER, allow_staff=True)
@require_POST
def review_vendor(request, pk):
    vendor = get_object_or_404(Vendor, pk=pk)
    decision = request.POST.get("decision")
    if decision == "approve":
        if vendor.requires_regulatory_license and not vendor.has_verified_license:
            messages.error(request, "A business licence must be verified before seller approval.")
            return redirect("dashboards:admin_dashboard")
        vendor.is_approved = True
        vendor.is_active = True
        message = f"{vendor.business_name} is now approved."
    elif decision == "suspend":
        vendor.is_approved = False
        vendor.is_active = False
        vendor.vendor_products.update(is_active=False)
        message = f"{vendor.business_name} and its offers were suspended."
    else:
        messages.error(request, "Invalid seller review action.")
        return redirect("dashboards:admin_dashboard")
    vendor.save(update_fields=["is_approved", "is_active", "updated_at"])
    record_audit(request, f"seller.{decision}", vendor, message)
    messages.success(request, message)
    return redirect("dashboards:admin_dashboard")


@role_required(UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.CATALOG_MANAGER, allow_staff=True)
@require_POST
def review_offer(request, pk):
    offer = get_object_or_404(VendorProduct.objects.select_related("product", "vendor"), pk=pk)
    decision = request.POST.get("decision")
    if decision == "approve":
        product = offer.product
        if product.requires_business_license:
            valid_licenses = offer.vendor.licenses.filter(status=BusinessLicense.Status.VERIFIED)
            if not any(
                license_record.is_compatible_with(product.required_license_type)
                for license_record in valid_licenses
            ):
                messages.error(
                    request,
                    "This regulated product needs a compatible verified seller licence before publication.",
                )
                return redirect("dashboards:admin_dashboard")
        offer.is_approved = True
        offer.is_active = True
        offer.product.is_active = True
        offer.product.save(update_fields=["is_active", "updated_at"])
        message = f"{offer.product.name} from {offer.vendor.business_name} is published."
    elif decision == "reject":
        offer.is_approved = False
        offer.is_active = False
        message = f"The offer for {offer.product.name} was rejected."
    else:
        messages.error(request, "Invalid catalog review action.")
        return redirect("dashboards:admin_dashboard")
    offer.save(update_fields=["is_approved", "is_active", "updated_at"])
    record_audit(request, f"offer.{decision}", offer, message)
    messages.success(request, message)
    return redirect("dashboards:admin_dashboard")


@role_required(UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.COMPLIANCE_OFFICER, allow_staff=True)
@require_POST
def review_business_license(request, pk):
    license_record = get_object_or_404(BusinessLicense.objects.select_related("vendor"), pk=pk)
    decision = request.POST.get("decision")
    notes = request.POST.get("notes", "").strip()[:2000]
    if decision == "approve":
        if not license_record.valid_until or license_record.valid_until < timezone.localdate():
            messages.error(request, "An expired licence or one without an expiry date cannot be verified.")
            return redirect("dashboards:admin_dashboard")
        if not license_record.document:
            messages.error(request, "A licence document is required before verification.")
            return redirect("dashboards:admin_dashboard")
        license_record.status = BusinessLicense.Status.VERIFIED
        message = f"Licence {license_record.license_number} was verified."
    elif decision == "reject":
        license_record.status = BusinessLicense.Status.REJECTED
        message = f"Licence {license_record.license_number} was rejected."
    else:
        messages.error(request, "Invalid licence review action.")
        return redirect("dashboards:admin_dashboard")
    license_record.reviewed_by = request.user
    license_record.reviewed_at = timezone.now()
    license_record.review_notes = notes
    license_record.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"]
    )
    record_audit(request, f"licence.{decision}", license_record, message, {"notes": notes})
    messages.success(request, message)
    return redirect("dashboards:admin_dashboard")
