from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
import json

from django.utils import timezone

from .models import ApprovalRequest


def queue_approval(target, action, requested_by, reason=""):
    content_type = ContentType.objects.get_for_model(target, for_concrete_model=False)
    return ApprovalRequest.objects.get_or_create(
        content_type=content_type,
        object_id=target.pk,
        action=action,
        status=ApprovalRequest.Status.PENDING,
        defaults={"requested_by": requested_by, "request_reason": reason[:2000]},
    )[0]


def apply_approval(approval, reviewer, decision, reason=""):
    if approval.status != ApprovalRequest.Status.PENDING:
        raise PermissionDenied("This approval has already been decided.")
    if approval.requested_by_id == reviewer.pk:
        raise PermissionDenied("A second authorized staff member must review this request.")
    target = approval.target
    approved = decision == ApprovalRequest.Status.APPROVED
    if approval.action.startswith("vendor."):
        target.is_approved = approved
        target.is_active = approved
        if not approved:
            target.vendor_products.update(is_active=False)
        target.save(update_fields=["is_approved", "is_active", "updated_at"])
    elif approval.action.startswith("offer."):
        target.is_approved = approved
        target.is_active = approved
        target.save(update_fields=["is_approved", "is_active", "updated_at"])
        if approved:
            target.product.is_active = True
            target.product.save(update_fields=["is_active", "updated_at"])
    elif approval.action.startswith("license."):
        target.status = target.Status.VERIFIED if approved else target.Status.REJECTED
        target.reviewed_by = reviewer
        target.reviewed_at = timezone.now()
        target.review_notes = reason[:2000]
        target.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])
    elif approval.action == "prescription.review":
        from prescriptions.models import Prescription

        try:
            request_data = json.loads(approval.request_reason or "{}")
        except (TypeError, ValueError):
            request_data = {}
        requested = request_data.get("requested_status")
        if not approved:
            target.status = Prescription.Status.UNDER_REVIEW
            target.clinical_validation_status = "pending"
            target.save(update_fields=["status", "clinical_validation_status", "updated_at"])
        elif requested == Prescription.Status.REJECTED:
            target.mark_rejected(reviewer, request_data.get("notes", "")[:2000])
        else:
            target.status = requested if requested in {
                Prescription.Status.APPROVED,
                Prescription.Status.PARTIALLY_APPROVED,
            } else Prescription.Status.APPROVED
            target.reviewed_by = reviewer
            target.reviewed_at = timezone.now()
            target.clinical_validation_status = "passed"
            target.save(update_fields=["status", "reviewed_by", "reviewed_at", "clinical_validation_status", "updated_at"])
    elif approval.action == "refund.retry":
        from orders.models import Refund

        if approved and target.status == Refund.Status.FAILED:
            target.status = Refund.Status.REQUESTED
            target.save(update_fields=["status", "updated_at"])
    else:
        raise PermissionDenied("This workflow has no maker-checker executor.")
    approval.status = decision
    approval.reviewed_by = reviewer
    approval.decision_reason = reason[:2000]
    approval.reviewed_at = timezone.now()
    approval.save(update_fields=["status", "reviewed_by", "decision_reason", "reviewed_at"])
    return target
