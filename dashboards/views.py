from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import UserProfile
from accounts.permissions import OPERATIONS_ROLES, role_allowed, role_required
from core.audit import record_audit
from orders.models import (
    Coupon,
    InventoryBatch,
    Order,
    OrderStatusHistory,
    Payment,
    Refund,
    Shipment,
    Warehouse,
)
from prescriptions.models import Prescription
from products.models import Brand, Category, Product
from extras.models import (
    BlogCategory,
    BlogPost,
    DoctorProfile,
    Notification,
    NotificationDelivery,
    SupportTicket,
)
from core.models import AuditEvent
from extras.services import create_notification
from vendors.models import BusinessLicense, Vendor, VendorProduct

from .forms import (
    BlogManagementForm,
    BlogCategoryManagementForm,
    BrandManagementForm,
    CategoryManagementForm,
    CouponManagementForm,
    ProductManagementForm,
    InventoryBatchManagementForm,
    ShipmentManagementForm,
    UserManagementForm,
    WarehouseManagementForm,
)

User = get_user_model()


SECTION_RULES = {
    "users": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER},
    "products": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.CATALOG_MANAGER},
    "categories": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.CATALOG_MANAGER},
    "brands": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.CATALOG_MANAGER},
    "vendors": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.COMPLIANCE_OFFICER},
    "licenses": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.COMPLIANCE_OFFICER},
    "offers": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.CATALOG_MANAGER, UserProfile.Role.WAREHOUSE_MANAGER},
    "orders": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.WAREHOUSE_MANAGER},
    "prescriptions": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER},
    "coupons": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER},
    "doctors": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER},
    "blog": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.CATALOG_MANAGER},
    "blog_categories": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.CATALOG_MANAGER},
    "support": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.SUPPORT_STAFF},
    "notifications": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.SUPPORT_STAFF},
    "notification_deliveries": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.SUPPORT_STAFF},
    "payments": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER},
    "refunds": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER},
    "warehouses": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.WAREHOUSE_MANAGER},
    "inventory": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.WAREHOUSE_MANAGER},
    "shipments": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.WAREHOUSE_MANAGER},
    "audit": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER},
}


def management_section_allowed(user, section):
    return section in SECTION_RULES and role_allowed(
        user,
        SECTION_RULES[section],
        allow_staff=True,
    )


def management_row(record, values, status_label="", status="", actions=None, edit_url="", view_url=""):
    return {
        "pk": record.pk,
        "values": values,
        "status_label": status_label,
        "status": status,
        "actions": actions or [],
        "edit_url": edit_url,
        "view_url": view_url,
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
    elif section == "licenses":
        records = BusinessLicense.objects.select_related("vendor", "reviewed_by").order_by("-updated_at")
        if query:
            records = records.filter(Q(license_number__icontains=query) | Q(vendor__business_name__icontains=query) | Q(legal_name__icontains=query))
        title = "Business Licences"
        columns = ["Business", "Licence", "Type", "Last reviewed"]
    elif section == "offers":
        records = VendorProduct.objects.select_related("product", "vendor").order_by("product__name")
        if query:
            records = records.filter(Q(product__name__icontains=query) | Q(vendor__business_name__icontains=query))
        title = "Seller Offers"
        columns = ["Product", "Seller", "Price", "Stock"]
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
    elif section == "notification_deliveries":
        records = NotificationDelivery.objects.select_related("notification", "notification__user").order_by("-created_at")
        if query:
            records = records.filter(Q(destination__icontains=query) | Q(notification__title__icontains=query))
        title = "Notification Delivery"
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
    elif section == "shipments":
        records = Shipment.objects.select_related("order", "warehouse").order_by("-updated_at")
        if query:
            records = records.filter(Q(order__order_number__icontains=query) | Q(tracking_number__icontains=query) | Q(courier_name__icontains=query))
        columns = ["Order", "Courier", "Tracking", "Promised"]
        create_url = reverse("dashboards:management_create", args=["shipments"])
        create_label = "shipment"
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
            rows.append(management_row(record, [record.business_name, record.get_business_type_display(), f"{record.email} · {record.phone}", record.license_number], "Approved" if record.is_approved and record.is_active else "Suspended", "active" if record.is_approved and record.is_active else "inactive", [("suspend" if record.is_active else "activate", "Suspend" if record.is_active else "Activate", "outline-danger" if record.is_active else "success")]))
        elif section == "licenses":
            rows.append(management_row(record, [record.vendor.business_name, f"{record.license_number} · {record.form_number or 'Form pending'}", record.get_license_type_display(), record.reviewed_at.strftime("%d %b %Y") if record.reviewed_at else "Not reviewed"], record.get_status_display(), record.status, view_url=reverse("core:license_document", args=[record.pk]) if record.document else ""))
        elif section == "offers":
            rows.append(management_row(record, [record.product.name, record.vendor.business_name, f"₹{record.price}", str(record.stock_quantity)], "Live" if record.is_active and record.is_approved else "Review required", "active" if record.is_active and record.is_approved else "pending", [("deactivate" if record.is_active else "activate", "Disable" if record.is_active else "Publish", "outline-danger" if record.is_active else "success")]))
        elif section == "orders":
            rows.append(management_row(record, [record.order_number, record.customer.get_full_name() or record.customer.username, f"₹{record.total_amount}", record.delivery_staff.get_full_name() if record.delivery_staff else "Unassigned"], record.get_order_status_display(), record.order_status))
        elif section == "prescriptions":
            actions = [] if record.status == Prescription.Status.APPROVED else [("approve", "Approve", "success"), ("reject", "Reject", "outline-danger")]
            rows.append(management_row(record, [f"#{record.pk}", record.user.get_full_name() or record.user.username, record.doctor_name or "Not provided", record.created_at.strftime("%d %b %Y")], record.get_status_display(), record.status, actions, view_url=reverse("core:prescription_file", args=[record.pk])))
        elif section == "coupons":
            discount = f"{record.discount_value}%" if record.discount_type == Coupon.DiscountType.PERCENTAGE else f"₹{record.discount_value}"
            rows.append(management_row(record, [record.code, discount, f"₹{record.minimum_order}", f"{record.start_date:%d %b} - {record.end_date:%d %b %Y}"], "Active" if record.is_active else "Inactive", "active" if record.is_active else "inactive", [("deactivate" if record.is_active else "activate", "Deactivate" if record.is_active else "Activate", "outline-danger" if record.is_active else "success")], reverse("dashboards:management_edit", args=["coupons", record.pk])))
        elif section == "doctors":
            rows.append(management_row(record, [record.full_name, record.specialization, f"{record.experience_years} years", record.clinic_name or "Not provided"], "Verified" if record.is_verified else "Pending", "active" if record.is_verified else "pending", [("unverify" if record.is_verified else "verify", "Remove verification" if record.is_verified else "Verify", "outline-danger" if record.is_verified else "success")], view_url=reverse("core:doctor_credential", args=[record.pk]) if record.qualification_document else ""))
        elif section == "blog":
            rows.append(management_row(record, [record.title, record.category.name if record.category else "Uncategorised", record.author.get_full_name() if record.author else "MediMart editorial", record.updated_at.strftime("%d %b %Y")], record.get_status_display(), record.status, [("draft" if record.status == BlogPost.Status.PUBLISHED else "publish", "Move to draft" if record.status == BlogPost.Status.PUBLISHED else "Publish", "outline-secondary" if record.status == BlogPost.Status.PUBLISHED else "success")], reverse("dashboards:management_edit", args=["blog", record.pk])))
        elif section == "blog_categories":
            rows.append(management_row(record, [record.name, str(record.post_count), record.description[:100] or "No description", record.slug], "Available", "active", edit_url=reverse("dashboards:management_edit", args=["blog_categories", record.pk])))
        elif section == "notifications":
            rows.append(management_row(record, [record.title, record.user.get_full_name() or record.user.username, record.get_notification_type_display(), record.created_at.strftime("%d %b %Y, %H:%M")], "Read" if record.is_read else "Unread", "active" if record.is_read else "pending", [("unread" if record.is_read else "read", "Mark unread" if record.is_read else "Mark read", "outline-secondary")]))
        elif section == "notification_deliveries":
            actions = [("retry", "Retry", "outline-success")] if record.status == NotificationDelivery.Status.FAILED else []
            rows.append(management_row(record, [record.notification.title, f"{record.get_channel_display()} · {record.destination}", str(record.attempts), record.next_attempt_at.strftime("%d %b %Y, %H:%M")], record.get_status_display(), record.status, actions))
        elif section == "payments":
            rows.append(management_row(record, [record.order.order_number, record.order.customer.get_full_name() or record.order.customer.username, f"₹{record.amount}", record.gateway_payment_id or record.gateway_order_id or "Not assigned"], record.get_status_display(), record.status))
        elif section == "refunds":
            actions = [("retry", "Retry", "outline-success")] if record.status == Refund.Status.FAILED else []
            rows.append(management_row(record, [record.payment.order.order_number, f"₹{record.amount}", record.reason, record.gateway_refund_id or "Not assigned"], record.get_status_display(), record.status, actions))
        elif section == "warehouses":
            rows.append(management_row(record, [record.code, record.name, record.pincode, record.address[:100]], "Active" if record.is_active else "Inactive", "active" if record.is_active else "inactive", [("deactivate" if record.is_active else "activate", "Deactivate" if record.is_active else "Activate", "outline-danger" if record.is_active else "success")], reverse("dashboards:management_edit", args=["warehouses", record.pk])))
        elif section == "inventory":
            available = max(0, record.quantity - record.reserved_quantity)
            rows.append(management_row(record, [f"{record.vendor_product.product.name} · {record.batch_number}", record.warehouse.name, f"{available} available / {record.quantity} total", record.expires_on.strftime("%d %b %Y") if record.expires_on else "Not set"], "Available" if available else "Depleted", "active" if available else "inactive", edit_url=reverse("dashboards:management_edit", args=["inventory", record.pk])))
        elif section == "shipments":
            rows.append(management_row(record, [record.order.order_number, record.courier_name or "Not assigned", record.tracking_number or "Not assigned", record.promised_at.strftime("%d %b %Y, %H:%M") if record.promised_at else "Not set"], record.get_status_display(), record.status, edit_url=reverse("dashboards:management_edit", args=["shipments", record.pk])))
        elif section == "audit":
            rows.append(management_row(record, [record.action, record.actor.get_full_name() or record.actor.username if record.actor else "System", f"{record.target_type} #{record.target_id}".strip(), record.summary or "No summary"], "Recorded", "active"))

    return render(request, "dashboards/management_records.html", {"section": section, "title": title, "description": description, "columns": columns, "rows": rows, "query": query, "page_obj": page_obj, "create_url": create_url, "create_label": create_label})


@role_required(*OPERATIONS_ROLES, allow_staff=True)
@require_POST
def management_record_action(request, section, pk):
    if not management_section_allowed(request.user, section):
        raise PermissionDenied
    action = request.POST.get("action")
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
    elif section == "blog":
        record = get_object_or_404(BlogPost, pk=pk)
        record.status = BlogPost.Status.PUBLISHED if action == "publish" else BlogPost.Status.DRAFT
        record.save(update_fields=["status", "published_at", "updated_at"])
    elif section == "notifications":
        record = get_object_or_404(Notification, pk=pk)
        record.is_read = action == "read"
        record.save(update_fields=["is_read"])
    elif section == "notification_deliveries":
        record = get_object_or_404(NotificationDelivery, pk=pk)
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
}


@role_required(*OPERATIONS_ROLES, allow_staff=True)
def management_form(request, section, pk=None):
    if section not in MANAGEMENT_FORMS or not management_section_allowed(request.user, section):
        raise PermissionDenied
    model, form_class, label = MANAGEMENT_FORMS[section]
    instance = get_object_or_404(model, pk=pk) if pk else None
    if section == "users" and instance and instance.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    if request.method == "POST":
        form = form_class(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            if section == "users":
                record = form.save()
            else:
                record = form.save(commit=False)
                if section == "blog" and not record.author_id:
                    record.author = request.user
                record.save()
                form.save_m2m()
            record_audit(
                request,
                f"management.{section}.{'updated' if instance else 'created'}",
                record,
                f"{label} saved from the Operations Center.",
            )
            messages.success(request, f"{label} saved successfully.")
            return redirect("dashboards:management_records", section=section)
    else:
        form = form_class(instance=instance)
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
        ("Health Guides", "blog", "journal-medical"),
        ("Guide Categories", "blog_categories", "collection"),
        ("Support", "support", "headset"),
        ("Notifications", "notifications", "bell"),
        ("Delivery Queue", "notification_deliveries", "send-check"),
        ("Payments", "payments", "credit-card"),
        ("Refunds", "refunds", "arrow-counterclockwise"),
        ("Warehouses", "warehouses", "building"),
        ("Inventory Batches", "inventory", "boxes"),
        ("Shipments", "shipments", "truck"),
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
            "can_view_financials": role_allowed(
                request.user,
                {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER},
                allow_staff=True,
            ),
            "can_review_licenses": role_allowed(
                request.user,
                {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.COMPLIANCE_OFFICER},
                allow_staff=True,
            ),
            "can_manage_catalog": role_allowed(
                request.user,
                {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.CATALOG_MANAGER},
                allow_staff=True,
            ),
            "can_manage_fulfillment": role_allowed(
                request.user,
                {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.WAREHOUSE_MANAGER},
                allow_staff=True,
            ),
            "can_manage_clinical": role_allowed(
                request.user,
                {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER},
                allow_staff=True,
            ),
            "can_manage_inventory": role_allowed(
                request.user,
                {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.WAREHOUSE_MANAGER},
                allow_staff=True,
            ),
            "can_manage_support": role_allowed(
                request.user,
                {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER, UserProfile.Role.SUPPORT_STAFF},
                allow_staff=True,
            ),
        },
    )


def user_can_access_delivery_dashboard(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and profile.role in {UserProfile.Role.DELIVERY_STAFF, UserProfile.Role.ADMIN})


@login_required
def delivery_dashboard(request):
    if not user_can_access_delivery_dashboard(request.user):
        messages.error(request, "Delivery dashboard access is limited to delivery staff.")
        return redirect("accounts:dashboard")

    active_orders = Order.objects.filter(
        order_status__in=[Order.OrderStatus.SHIPPED, Order.OrderStatus.OUT_FOR_DELIVERY]
    ).select_related("customer", "address")
    delivered_orders = Order.objects.filter(order_status=Order.OrderStatus.DELIVERED)
    if not request.user.is_superuser and getattr(request.user.profile, "role", None) == UserProfile.Role.DELIVERY_STAFF:
        active_orders = active_orders.filter(delivery_staff=request.user)
        delivered_orders = delivered_orders.filter(delivery_staff=request.user)

    stats = {
        "assigned_orders": active_orders.count(),
        "out_for_delivery": active_orders.filter(
            order_status=Order.OrderStatus.OUT_FOR_DELIVERY
        ).count(),
        "delivered_today": delivered_orders.filter(updated_at__date=timezone.localdate()).count(),
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
        messages.error(request, "Delivery dashboard access is limited to delivery staff.")
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
