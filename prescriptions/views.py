from django.contrib import messages
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import has_capability
from accounts.models import UserProfile
from core.audit import record_audit
from extras.models import Notification
from extras.services import create_notification

from .forms import PrescriptionItemFormSet, PrescriptionReviewForm, PrescriptionUploadForm
from .models import Prescription, PrescriptionItem, PrescriptionReview
from .services import scan_uploaded_prescription


def user_has_approved_prescription(user, product=None, quantity=1):
    if not user.is_authenticated:
        return False
    prescriptions = user.prescriptions.filter(
        status__in=[Prescription.Status.APPROVED, Prescription.Status.PARTIALLY_APPROVED],
        valid_until__gte=timezone.localdate(),
    ).prefetch_related("items")
    if product is None:
        return any(prescription.is_current for prescription in prescriptions)
    return any(
        prescription.authorizes(product, quantity)
        for prescription in prescriptions
    )


def can_review_prescriptions(user):
    if not has_capability(user, "clinical.prescription_review"):
        return False
    profile = getattr(user, "profile", None)
    if profile and profile.role == UserProfile.Role.PHARMACIST:
        return bool(getattr(getattr(user, "pharmacist_profile", None), "is_verified", False))
    return True

@login_required
def prescription_list(request):
    prescriptions = request.user.prescriptions.prefetch_related("items", "revisions").all()
    return render(
        request,
        "prescriptions/prescription_list.html",
        {"prescriptions": prescriptions},
    )


@login_required
def prescription_upload(request):
    if request.method == "POST":
        form = PrescriptionUploadForm(request.POST, request.FILES)
        if form.is_valid():
            prescription = form.save(commit=False)
            prescription.user = request.user
            prescription.save()
            scan_uploaded_prescription(prescription)
            record_audit(
                request,
                "prescription.uploaded",
                prescription,
                "Prescription submitted for secure review.",
            )
            create_notification(
                request.user,
                "Prescription uploaded",
                "Your prescription was uploaded and is pending review.",
                Notification.NotificationType.PRESCRIPTION,
                prescription.get_absolute_url(),
            )
            messages.success(
                request,
                "Prescription uploaded successfully and is pending review.",
            )
            return redirect("prescriptions:prescription_detail", pk=prescription.pk)
    else:
        profile = getattr(request.user, "profile", None)
        form = PrescriptionUploadForm(
            initial={
                "patient_name": request.user.get_full_name() or request.user.username,
                "patient_date_of_birth": getattr(profile, "date_of_birth", None),
                "patient_gender": getattr(profile, "gender", ""),
            }
        )

    return render(request, "prescriptions/prescription_upload.html", {"form": form})


@login_required
def prescription_detail(request, pk):
    prescription = get_object_or_404(
        Prescription.objects.select_related("reviewed_by", "supersedes").prefetch_related(
            "items__product",
            "revisions",
        ),
        pk=pk,
        user=request.user,
    )
    return render(
        request,
        "prescriptions/prescription_detail.html",
        {"prescription": prescription},
    )


@login_required
def prescription_resubmit(request, pk):
    original = get_object_or_404(Prescription, pk=pk, user=request.user)
    if not original.needs_customer_action:
        messages.info(request, "This prescription does not currently need a replacement.")
        return redirect(original)

    initial = {
        "patient_name": original.patient_name,
        "patient_date_of_birth": original.patient_date_of_birth,
        "patient_gender": original.patient_gender,
        "doctor_name": original.doctor_name,
        "doctor_registration_number": original.doctor_registration_number,
        "clinic_name": original.clinic_name,
        "clinic_contact": original.clinic_contact,
        "prescription_date": original.prescription_date,
        "requested_medicines": original.requested_medicines,
        "notes": original.notes,
    }
    form = PrescriptionUploadForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        prescription = form.save(commit=False)
        prescription.user = request.user
        prescription.supersedes = original
        prescription.save()
        scan_uploaded_prescription(prescription)
        record_audit(
            request,
            "prescription.resubmitted",
            prescription,
            f"Replacement submitted for prescription #{original.pk}.",
        )
        create_notification(
            request.user,
            "Replacement prescription received",
            f"Prescription #{prescription.pk} is queued for review.",
            Notification.NotificationType.PRESCRIPTION,
            prescription.get_absolute_url(),
        )
        messages.success(request, "Replacement prescription submitted for review.")
        return redirect(prescription)
    return render(
        request,
        "prescriptions/prescription_upload.html",
        {"form": form, "replacement_for": original},
    )


@login_required
@require_POST
def prescription_cancel(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk, user=request.user)
    if prescription.status not in {
        Prescription.Status.PENDING,
        Prescription.Status.UNDER_REVIEW,
        Prescription.Status.NEEDS_INFORMATION,
    }:
        messages.error(request, "This prescription can no longer be cancelled.")
        return redirect(prescription)
    prescription.status = Prescription.Status.CANCELLED
    prescription.save(update_fields=["status", "updated_at"])
    record_audit(
        request,
        "prescription.cancelled",
        prescription,
        "Customer cancelled prescription review.",
    )
    messages.success(request, "Prescription review cancelled.")
    return redirect(prescription)


@login_required
def prescription_review(request, pk):
    if not can_review_prescriptions(request.user):
        raise PermissionDenied
    prescription = get_object_or_404(
        Prescription.objects.select_related("user", "reviewed_by").prefetch_related("items__product"),
        pk=pk,
    )
    form = PrescriptionReviewForm(request.POST or None, instance=prescription)
    formset = PrescriptionItemFormSet(
        request.POST or None,
        instance=prescription,
        prefix="items",
    )
    if request.method == "POST":
        form_valid = form.is_valid()
        formset_valid = formset.is_valid()
        if form_valid and formset_valid:
            active_items = [
                item_form
                for item_form in formset.forms
                if item_form.cleaned_data
                and not item_form.cleaned_data.get("DELETE")
                and item_form.cleaned_data.get("product")
            ]
            if form.cleaned_data["status"] == Prescription.Status.APPROVED and not active_items:
                form.add_error(None, "Map at least one product before approving this prescription.")
                form_valid = False
            if form.cleaned_data["status"] == Prescription.Status.APPROVED and any(
                item_form.cleaned_data.get("approval_status")
                != PrescriptionItem.ApprovalStatus.APPROVED
                for item_form in active_items
            ):
                form.add_error(
                    "status",
                    "Approve every item or choose Partially Approved so rejected items cannot be dispensed.",
                )
                form_valid = False
            if form.cleaned_data["status"] == Prescription.Status.PARTIALLY_APPROVED and not any(
                item_form.cleaned_data.get("approval_status") == PrescriptionItem.ApprovalStatus.APPROVED
                for item_form in active_items
            ):
                form.add_error("status", "At least one prescription item must be approved.")
                form_valid = False
            if form.cleaned_data["status"] in {
                Prescription.Status.APPROVED,
                Prescription.Status.PARTIALLY_APPROVED,
            }:
                validation_items = [
                    {
                        "approval_status": item_form.cleaned_data.get("approval_status"),
                        "dosage": item_form.cleaned_data.get("dosage"),
                        "duration_days": item_form.cleaned_data.get("duration_days"),
                        "quantity": item_form.cleaned_data.get("quantity"),
                    }
                    for item_form in active_items
                ]
                validation_flags = prescription.compute_validation_flags(items=validation_items)
                if validation_flags:
                    form.add_error(
                        "status",
                        "Approval is blocked until the prescription checks are complete: "
                        + ", ".join(validation_flags),
                    )
                    form_valid = False
        if form_valid and formset_valid:
            with transaction.atomic():
                prescription = form.save(commit=False)
                prescription.validation_flags = prescription.compute_validation_flags(
                    items=[
                        {
                            "approval_status": item_form.cleaned_data.get("approval_status"),
                            "dosage": item_form.cleaned_data.get("dosage"),
                            "duration_days": item_form.cleaned_data.get("duration_days"),
                            "quantity": item_form.cleaned_data.get("quantity"),
                        }
                        for item_form in formset.forms
                        if item_form.cleaned_data
                        and not item_form.cleaned_data.get("DELETE")
                        and item_form.cleaned_data.get("product")
                    ]
                )
                if prescription.status in {
                    Prescription.Status.APPROVED,
                    Prescription.Status.PARTIALLY_APPROVED,
                }:
                    prescription.clinical_validation_status = "passed"
                prescription.reviewed_by = request.user
                prescription.reviewed_at = timezone.now()
                prescription.save()
                saved_items = formset.save(commit=False)
                for item in saved_items:
                    item.reviewed_by = request.user
                    item.reviewed_at = timezone.now()
                    item.save()
                for deleted_item in formset.deleted_objects:
                    deleted_item.delete()
                formset.save_m2m()
                PrescriptionReview.objects.create(
                    prescription=prescription,
                    reviewer=request.user,
                    decision=(
                        PrescriptionReview.Decision.UNDER_REVIEW
                        if prescription.status == Prescription.Status.PENDING
                        else prescription.status
                    ),
                    pharmacy_license_number=getattr(
                        getattr(request.user, "pharmacist_profile", None),
                        "pharmacy_license_number",
                        "",
                    ),
                    notes=prescription.review_notes or prescription.clarification_message or prescription.rejection_reason,
                    validation_snapshot={
                        "prescriber_verified": prescription.prescriber_verified,
                        "patient_identity_verified": prescription.patient_identity_verified,
                        "clinical_validation_status": prescription.clinical_validation_status,
                    },
                )
            record_audit(
                request,
                "prescription.reviewed",
                prescription,
                f"Prescription moved to {prescription.get_status_display()}.",
            )
            create_notification(
                prescription.user,
                "Prescription review updated",
                f"Prescription #{prescription.pk} is now {prescription.get_status_display().lower()}.",
                Notification.NotificationType.PRESCRIPTION,
                prescription.get_absolute_url(),
            )
            messages.success(request, "Prescription review saved.")
            return redirect("dashboards:management_records", section="prescriptions")
    return render(
        request,
        "prescriptions/prescription_review.html",
        {"prescription": prescription, "form": form, "formset": formset},
    )
