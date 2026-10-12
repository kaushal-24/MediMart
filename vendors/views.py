from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import UserProfile
from orders.models import Order, OrderItem

from .forms import (
    BusinessLicenseForm,
    VendorCatalogProductForm,
    VendorProductForm,
    VendorRegistrationForm,
)
from .models import BusinessLicense, Vendor, VendorProduct


def vendor_list(request):
    vendors = Vendor.objects.filter(is_active=True, is_approved=True)
    return render(request, "vendors/vendor_list.html", {"vendors": vendors})


def vendor_detail(request, pk):
    vendor = get_object_or_404(Vendor, pk=pk, is_active=True, is_approved=True)
    offers = vendor.vendor_products.filter(is_active=True, is_approved=True).select_related(
        "product",
        "product__brand",
        "product__category",
    )
    return render(
        request,
        "vendors/vendor_detail.html",
        {
            "vendor": vendor,
            "offers": offers,
        },
    )


@login_required
def vendor_register(request):
    if hasattr(request.user, "vendor_profile"):
        return redirect("vendors:vendor_dashboard")

    if request.method == "POST":
        form = VendorRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                vendor = form.save(commit=False)
                vendor.user = request.user
                vendor.save()
                BusinessLicense.objects.create(
                    vendor=vendor,
                    license_type=form.cleaned_data["license_type"],
                    license_number=form.cleaned_data["license_number"],
                    form_number=form.cleaned_data.get("license_form_number", ""),
                    legal_name=form.cleaned_data.get("license_legal_name", "") or vendor.business_name,
                    premises_address=vendor.address,
                    state=form.cleaned_data.get("license_state", ""),
                    issued_on=form.cleaned_data.get("license_issued_on"),
                    valid_until=form.cleaned_data.get("license_valid_until"),
                    document=form.cleaned_data.get("license_document"),
                )
                profile, created = UserProfile.objects.get_or_create(user=request.user)
                if profile.role != UserProfile.Role.MANUFACTURER:
                    profile.role = (
                        UserProfile.Role.PHARMACY
                        if vendor.business_type == Vendor.BusinessType.PHARMACY
                        else UserProfile.Role.VENDOR
                    )
                profile.save()
            messages.success(request, "Your vendor registration has been submitted for manual compliance review.")
            return redirect("vendors:vendor_dashboard")
    else:
        initial = {
            "owner_name": request.user.get_full_name() or request.user.username,
            "email": request.user.email,
        }
        profile = getattr(request.user, "profile", None)
        if profile and profile.role == UserProfile.Role.MANUFACTURER:
            initial["business_type"] = Vendor.BusinessType.MANUFACTURER
        form = VendorRegistrationForm(initial=initial)

    return render(request, "vendors/vendor_register.html", {"form": form})


@login_required
def vendor_dashboard(request):
    vendor = getattr(request.user, "vendor_profile", None)
    if not vendor:
        messages.info(request, "Register your business before using the vendor dashboard.")
        return redirect("vendors:vendor_register")

    offers = vendor.vendor_products.select_related("product")
    order_items = OrderItem.objects.filter(vendor=vendor).select_related(
        "order",
        "product",
    )
    recognized_items = order_items.filter(
        Q(order__payment_status=Order.PaymentStatus.PAID)
        | Q(order__order_status=Order.OrderStatus.DELIVERED)
    ).exclude(order__order_status__in=[Order.OrderStatus.CANCELLED, Order.OrderStatus.RETURNED])
    sales = recognized_items.aggregate(
        revenue=Sum("total_price"),
        units=Sum("quantity"),
    )
    fulfillment_items = order_items.filter(
        order__order_status__in=[
            Order.OrderStatus.CONFIRMED,
            Order.OrderStatus.PROCESSING,
            Order.OrderStatus.PACKED,
        ]
    )
    stats = {
        "total_products": offers.count(),
        "active_products": offers.filter(is_active=True).count(),
        "approved_products": offers.filter(is_approved=True).count(),
        "pending_products": offers.filter(is_approved=False).count(),
        "low_stock": offers.filter(stock_quantity__lte=5).count(),
        "total_stock": offers.aggregate(total=Sum("stock_quantity"))["total"] or 0,
        "revenue": sales["revenue"] or 0,
        "units_sold": sales["units"] or 0,
        "orders_to_fulfill": fulfillment_items.values("order_id").distinct().count(),
    }

    return render(
        request,
        "vendors/vendor_dashboard.html",
        {
            "vendor": vendor,
            "stats": stats,
            "recent_offers": offers[:5],
            "recent_order_items": order_items.order_by("-order__created_at")[:8],
            "licenses": vendor.licenses.all(),
        },
    )


@login_required
def business_license_list(request):
    vendor = get_vendor_or_redirect(request)
    if not isinstance(vendor, Vendor):
        return vendor
    return render(
        request,
        "vendors/business_license_list.html",
        {
            "vendor": vendor,
            "licenses": vendor.licenses.all(),
        },
    )


@login_required
def business_license_create(request):
    vendor = get_vendor_or_redirect(request)
    if not isinstance(vendor, Vendor):
        return vendor
    if request.method == "POST":
        form = BusinessLicenseForm(request.POST, request.FILES)
        if form.is_valid():
            license_record = form.save(commit=False)
            license_record.vendor = vendor
            license_record.status = BusinessLicense.Status.PENDING
            license_record.verification_source = BusinessLicense.VerificationSource.APPLICANT
            license_record.save()
            messages.success(request, "Licence submitted for manual compliance review.")
            return redirect("vendors:business_license_list")
    else:
        form = BusinessLicenseForm(initial={"legal_name": vendor.business_name})
    return render(request, "vendors/business_license_form.html", {"form": form, "vendor": vendor})


@login_required
def vendor_product_list(request):
    vendor = get_vendor_or_redirect(request)
    if not isinstance(vendor, Vendor):
        return vendor

    offers = vendor.vendor_products.select_related("product", "product__brand").all()
    return render(
        request,
        "vendors/vendor_product_list.html",
        {
            "vendor": vendor,
            "offers": offers,
        },
    )


@login_required
def vendor_product_create(request):
    vendor = get_vendor_or_redirect(request)
    if not isinstance(vendor, Vendor):
        return vendor

    if request.method == "POST":
        form = VendorProductForm(request.POST)
        if form.is_valid():
            selected_product = form.cleaned_data["product"]
            if VendorProduct.objects.filter(vendor=vendor, product=selected_product).exists():
                form.add_error("product", "You already have an offer for this product.")
            else:
                offer = form.save(commit=False)
                offer.vendor = vendor
                offer.is_approved = False
                offer.save()
                messages.success(request, "Product offer submitted for admin approval.")
                return redirect("vendors:vendor_product_list")
    else:
        form = VendorProductForm()

    return render(
        request,
        "vendors/vendor_product_form.html",
        {
            "form": form,
            "page_title": "Add Product Offer",
        },
    )


@login_required
def vendor_catalog_product_create(request):
    vendor = get_vendor_or_redirect(request)
    if not isinstance(vendor, Vendor):
        return vendor

    if request.method == "POST":
        form = VendorCatalogProductForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                product = form.save(commit=False)
                product.is_active = False
                if product.required_license_type == product.RegulationType.NONE:
                    product.requires_business_license = False
                if not product.manufacturer:
                    product.manufacturer = vendor.business_name
                product.save()
                VendorProduct.objects.create(
                    vendor=vendor,
                    product=product,
                    price=product.selling_price,
                    stock_quantity=product.stock_quantity,
                    delivery_time="2-4 days",
                    warranty=request.POST.get("warranty", ""),
                    offer_text="New catalog submission",
                    is_active=True,
                    is_approved=False,
                )
            messages.success(
                request,
                "Product submitted. Admin approval will publish the catalog item and seller offer.",
            )
            return redirect("vendors:vendor_product_list")
    else:
        form = VendorCatalogProductForm(
            initial={
                "manufacturer": vendor.business_name,
                "product_type": (
                    "medical_equipment"
                    if vendor.business_type == Vendor.BusinessType.MANUFACTURER
                    else ""
                ),
            }
        )

    return render(
        request,
        "vendors/vendor_catalog_product_form.html",
        {
            "form": form,
            "vendor": vendor,
        },
    )


@login_required
def vendor_product_update(request, pk):
    vendor = get_vendor_or_redirect(request)
    if not isinstance(vendor, Vendor):
        return vendor

    offer = get_object_or_404(VendorProduct, pk=pk, vendor=vendor)

    if request.method == "POST":
        form = VendorProductForm(request.POST, instance=offer)
        if form.is_valid():
            selected_product = form.cleaned_data["product"]
            duplicate_exists = VendorProduct.objects.filter(
                vendor=vendor,
                product=selected_product,
            ).exclude(pk=offer.pk).exists()
            if duplicate_exists:
                form.add_error("product", "You already have another offer for this product.")
            else:
                offer = form.save(commit=False)
                offer.is_approved = False
                offer.save()
                messages.success(request, "Product offer updated and sent for approval.")
                return redirect("vendors:vendor_product_list")
    else:
        form = VendorProductForm(instance=offer)

    return render(
        request,
        "vendors/vendor_product_form.html",
        {
            "form": form,
            "page_title": "Edit Product Offer",
        },
    )


@login_required
def vendor_product_delete(request, pk):
    vendor = get_vendor_or_redirect(request)
    if not isinstance(vendor, Vendor):
        return vendor

    offer = get_object_or_404(VendorProduct, pk=pk, vendor=vendor)
    if request.method == "POST":
        if offer.order_items.exists():
            offer.is_active = False
            offer.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Product offer archived because it has order history.")
        else:
            offer.delete()
            messages.success(request, "Product offer deleted.")
        return redirect("vendors:vendor_product_list")

    return render(request, "vendors/vendor_product_confirm_delete.html", {"offer": offer})


def get_vendor_or_redirect(request):
    vendor = getattr(request.user, "vendor_profile", None)
    if not vendor:
        messages.info(request, "Register as a vendor first.")
        return redirect("vendors:vendor_register")
    return vendor
