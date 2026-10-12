from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404

from accounts.models import UserProfile
from accounts.permissions import role_allowed
from extras.models import DoctorProfile, SupportMessage, SupportTicket
from healthcare.models import ConsultationMessage, HealthRecord, LabBooking
from prescriptions.models import Prescription
from vendors.models import BusinessLicense, Vendor


CLINICAL_ROLES = {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS_MANAGER}
COMPLIANCE_ROLES = {
    UserProfile.Role.ADMIN,
    UserProfile.Role.OPERATIONS_MANAGER,
    UserProfile.Role.COMPLIANCE_OFFICER,
}
SUPPORT_ROLES = {
    UserProfile.Role.ADMIN,
    UserProfile.Role.OPERATIONS_MANAGER,
    UserProfile.Role.SUPPORT_STAFF,
}


def _download(field, *, inline=False):
    if not field or not field.name:
        raise Http404("File not found.")
    try:
        stream = field.storage.open(field.name, "rb")
    except (FileNotFoundError, OSError):
        raise Http404("File not found.")
    return FileResponse(
        stream,
        as_attachment=not inline,
        filename=Path(field.name).name,
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )


@login_required
def prescription_file(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk)
    if prescription.user_id != request.user.id and not role_allowed(request.user, CLINICAL_ROLES):
        raise PermissionDenied
    return _download(prescription.file, inline=True)


@login_required
def vendor_document(request, pk):
    vendor = get_object_or_404(Vendor, pk=pk)
    if vendor.user_id != request.user.id and not role_allowed(request.user, COMPLIANCE_ROLES):
        raise PermissionDenied
    return _download(vendor.documents)


@login_required
def license_document(request, pk):
    license_record = get_object_or_404(BusinessLicense.objects.select_related("vendor"), pk=pk)
    if license_record.vendor.user_id != request.user.id and not role_allowed(request.user, COMPLIANCE_ROLES):
        raise PermissionDenied
    return _download(license_record.document, inline=True)


@login_required
def support_ticket_attachment(request, pk):
    ticket = get_object_or_404(SupportTicket, pk=pk)
    if ticket.user_id != request.user.id and not role_allowed(request.user, SUPPORT_ROLES):
        raise PermissionDenied
    return _download(ticket.attachment)


@login_required
def support_message_attachment(request, pk):
    message = get_object_or_404(SupportMessage.objects.select_related("ticket"), pk=pk)
    if message.ticket.user_id != request.user.id and not role_allowed(request.user, SUPPORT_ROLES):
        raise PermissionDenied
    return _download(message.attachment)


@login_required
def doctor_credential(request, pk):
    doctor = get_object_or_404(DoctorProfile, pk=pk)
    if doctor.user_id != request.user.id and not role_allowed(request.user, CLINICAL_ROLES):
        raise PermissionDenied
    return _download(doctor.qualification_document, inline=True)


@login_required
def health_record_file(request, pk):
    record = get_object_or_404(HealthRecord, pk=pk)
    if record.user_id != request.user.id and not role_allowed(request.user, CLINICAL_ROLES):
        raise PermissionDenied
    return _download(record.document, inline=True)


@login_required
def lab_report_file(request, pk):
    booking = get_object_or_404(LabBooking, pk=pk)
    if booking.user_id != request.user.id and not role_allowed(request.user, CLINICAL_ROLES):
        raise PermissionDenied
    return _download(booking.report_file, inline=True)


@login_required
def consultation_attachment(request, pk):
    message = get_object_or_404(
        ConsultationMessage.objects.select_related("consultation__doctor"),
        pk=pk,
    )
    consultation = message.consultation
    is_participant = (
        consultation.user_id == request.user.id
        or consultation.doctor.user_id == request.user.id
    )
    if not is_participant and not role_allowed(request.user, CLINICAL_ROLES):
        raise PermissionDenied
    return _download(message.attachment)
