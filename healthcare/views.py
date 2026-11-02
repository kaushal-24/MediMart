from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.audit import record_audit
from accounts.models import UserProfile
from extras.models import DoctorProfile, Notification
from extras.services import create_notification

from .forms import ConsultationFollowUpForm, ConsultationForm, ConsultationMessageForm, DependentForm, HealthRecordForm, LabBookingForm, LabDisputeForm, LabRescheduleForm, MedicationReminderForm
from .models import (
    Consultation,
    ConsultationMessage,
    ConsultationPayment,
    DoctorAvailability,
    HealthRecord,
    LabBooking,
    LabCollectionSlot,
    LabDispute,
    LabInvoice,
    LabSampleEvent,
    LabTest,
    MedicationReminder,
)
from .services import (
    consultation_payment_is_configured,
    consultation_room_url,
    create_consultation_payment_order,
    refund_consultation_payment,
    schedule_consultation_followup,
    verify_consultation_payment,
)


@login_required
def health_dashboard(request):
    return render(request, "healthcare/dashboard.html", {
        "dependents": request.user.dependents.filter(is_active=True),
        "records": request.user.health_records.filter(is_archived=False)[:5],
        "reminders": request.user.medication_reminders.filter(is_active=True)[:5],
        "lab_bookings": request.user.lab_bookings.select_related("lab_test", "lab_test__partner")[:5],
        "consultations": request.user.consultations.select_related("doctor")[:5],
    })


@login_required
def dependent_list(request):
    dependents = request.user.dependents.filter(is_active=True)
    form = DependentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dependent = form.save(commit=False)
        dependent.user = request.user
        dependent.save()
        messages.success(request, "Family member added.")
        return redirect("healthcare:dependents")
    return render(request, "healthcare/dependents.html", {"dependents": dependents, "form": form})


def lab_list(request):
    query = request.GET.get("q", "").strip()
    tests = LabTest.objects.filter(is_active=True, partner__is_active=True).select_related("partner")
    if query:
        tests = tests.filter(Q(name__icontains=query) | Q(partner__name__icontains=query) | Q(partner__city__icontains=query))
    page_obj = Paginator(tests, 12).get_page(request.GET.get("page"))
    return render(request, "healthcare/lab_list.html", {"tests": page_obj.object_list, "page_obj": page_obj, "query": query})


@login_required
def lab_booking_create(request, pk=None):
    test = LabTest.objects.filter(
        pk=pk,
        is_active=True,
        partner__is_active=True,
    ).first() if pk else None
    if pk and not test:
        return redirect("healthcare:labs")
    form = LabBookingForm(request.POST or None, user=request.user, lab_test=test)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            booking = form.save(commit=False)
            booking.user = request.user
            if booking.slot_id:
                slot = LabCollectionSlot.objects.select_for_update().get(pk=booking.slot_id)
                if slot.is_blackout or not slot.is_active or slot.available_capacity <= 0:
                    form.add_error("slot", "That collection slot was just booked. Choose another slot.")
                    return render(request, "healthcare/lab_booking_form.html", {"form": form, "selected_test": test})
                booking.scheduled_start = slot.starts_at
                booking.scheduled_end = slot.ends_at
                slot.booked_count += 1
                slot.save(update_fields=["booked_count"])
            booking.save()
            LabInvoice.objects.create(
                booking=booking,
                subtotal=booking.lab_test.price,
                total_amount=booking.lab_test.price,
            )
            LabSampleEvent.objects.create(
                booking=booking,
                event_type=LabSampleEvent.EventType.REQUESTED,
                barcode=booking.accession_number,
                note="Booking created; sample not yet collected.",
            )
        record_audit(request, "healthcare.lab_booking.created", booking, "Lab booking requested.")
        messages.success(request, "Lab booking request submitted. The partner will confirm your slot.")
        return redirect("healthcare:lab_bookings")
    return render(request, "healthcare/lab_booking_form.html", {"form": form, "selected_test": test})


@login_required
def lab_booking_list(request):
    bookings = request.user.lab_bookings.select_related("lab_test", "lab_test__partner", "dependent", "invoice")
    return render(request, "healthcare/lab_bookings.html", {"bookings": bookings})


@login_required
def lab_booking_detail(request, pk):
    booking = get_object_or_404(
        LabBooking.objects.select_related("lab_test", "lab_test__partner", "dependent", "invoice").prefetch_related("report_values", "sample_events", "disputes"),
        pk=pk,
        user=request.user,
    )
    return render(request, "healthcare/lab_booking_detail.html", {"booking": booking, "disputes": booking.disputes.all()})


@login_required
def lab_booking_dispute(request, pk):
    booking = get_object_or_404(LabBooking, pk=pk, user=request.user)
    form = LabDisputeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dispute = form.save(commit=False)
        dispute.booking = booking
        dispute.raised_by = request.user
        dispute.save()
        create_notification(
            request.user,
            "Lab dispute submitted",
            f"Your dispute for lab booking {booking.accession_number} was submitted for review.",
            Notification.NotificationType.SUPPORT,
            reverse("healthcare:lab_booking_detail", args=[booking.pk]),
        )
        messages.success(request, "Your lab dispute was submitted for review.")
        return redirect("healthcare:lab_booking_detail", pk=pk)
    return render(request, "healthcare/form.html", {"form": form, "title": "Report a lab issue", "eyebrow": "Diagnostics"})


@login_required
@require_POST
def lab_booking_cancel(request, pk):
    with transaction.atomic():
        booking = get_object_or_404(
            LabBooking.objects.select_for_update(),
            pk=pk,
            user=request.user,
        )
        if booking.status not in {LabBooking.Status.REQUESTED, LabBooking.Status.CONFIRMED}:
            messages.error(request, "This booking can no longer be cancelled online.")
            return redirect("healthcare:lab_bookings")
        if booking.slot_id:
            slot = LabCollectionSlot.objects.select_for_update().get(pk=booking.slot_id)
            slot.booked_count = max(0, slot.booked_count - 1)
            slot.save(update_fields=["booked_count"])
        booking.status = LabBooking.Status.CANCELLED
        booking.cancellation_reason = "Cancelled by customer."
        booking.save(update_fields=["status", "cancellation_reason", "updated_at"])
        LabSampleEvent.objects.create(
            booking=booking,
            event_type=LabSampleEvent.EventType.CANCELLED,
            barcode=booking.accession_number,
            note=booking.cancellation_reason,
            recorded_by=request.user,
        )
    record_audit(request, "healthcare.lab_booking.cancelled", booking, "Lab booking cancelled by customer.")
    messages.success(request, "Your lab booking has been cancelled.")
    return redirect("healthcare:lab_bookings")


@login_required
def lab_booking_reschedule(request, pk):
    booking = get_object_or_404(
        LabBooking.objects.select_related("lab_test", "lab_test__partner", "slot"),
        pk=pk,
        user=request.user,
    )
    if booking.status not in {LabBooking.Status.REQUESTED, LabBooking.Status.CONFIRMED}:
        messages.error(request, "This booking can no longer be rescheduled online.")
        return redirect("healthcare:lab_bookings")
    form = LabRescheduleForm(request.POST or None, booking=booking)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            locked_booking = LabBooking.objects.select_for_update().get(pk=booking.pk)
            old_slot = LabCollectionSlot.objects.select_for_update().get(pk=locked_booking.slot_id) if locked_booking.slot_id else None
            new_slot = LabCollectionSlot.objects.select_for_update().get(pk=form.cleaned_data["slot"].pk)
            if new_slot.is_blackout or not new_slot.is_active or new_slot.available_capacity <= 0:
                form.add_error("slot", "That collection slot was just booked. Choose another slot.")
            else:
                if old_slot and old_slot.pk != new_slot.pk:
                    old_slot.booked_count = max(0, old_slot.booked_count - 1)
                    old_slot.save(update_fields=["booked_count"])
                    new_slot.booked_count += 1
                    new_slot.save(update_fields=["booked_count"])
                locked_booking.slot = new_slot
                locked_booking.scheduled_start = new_slot.starts_at
                locked_booking.scheduled_end = new_slot.ends_at
                locked_booking.save(update_fields=["slot", "scheduled_start", "scheduled_end", "updated_at"])
                LabSampleEvent.objects.create(
                    booking=locked_booking,
                    event_type=LabSampleEvent.EventType.REQUESTED,
                    barcode=locked_booking.accession_number,
                    note="Collection slot rescheduled by customer.",
                    recorded_by=request.user,
                )
                record_audit(request, "healthcare.lab_booking.rescheduled", locked_booking, "Lab booking slot rescheduled.")
                messages.success(request, "Your lab collection slot has been rescheduled.")
                return redirect("healthcare:lab_bookings")
    return render(request, "healthcare/lab_booking_reschedule.html", {"form": form, "booking": booking})


@login_required
def health_record_list(request):
    records = request.user.health_records.select_related("dependent").filter(is_archived=False)
    return render(request, "healthcare/records.html", {"records": records})


@login_required
def health_record_create(request):
    form = HealthRecordForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        record.user = request.user
        record.save()
        record_audit(request, "healthcare.record.created", record, "Health record uploaded.")
        messages.success(request, "Health record uploaded securely.")
        return redirect("healthcare:records")
    return render(request, "healthcare/form.html", {"form": form, "title": "Add health record", "eyebrow": "Health records"})


@login_required
def reminder_list(request):
    reminders = request.user.medication_reminders.select_related("dependent", "product")
    form = MedicationReminderForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        reminder = form.save(commit=False)
        reminder.user = request.user
        reminder.save()
        messages.success(request, "Medication reminder saved.")
        return redirect("healthcare:reminders")
    return render(request, "healthcare/reminders.html", {"reminders": reminders, "form": form})


@login_required
@require_POST
def reminder_toggle(request, pk):
    reminder = get_object_or_404(MedicationReminder, pk=pk, user=request.user)
    reminder.is_active = not reminder.is_active
    reminder.save(update_fields=["is_active", "updated_at"])
    return redirect("healthcare:reminders")


@login_required
def consultation_list(request):
    if getattr(getattr(request.user, "profile", None), "role", None) == UserProfile.Role.DOCTOR:
        doctor = DoctorProfile.objects.filter(user=request.user).first()
        consultations = (
            Consultation.objects.filter(doctor=doctor).select_related("doctor", "dependent", "user")
            if doctor
            else Consultation.objects.none()
        )
    else:
        consultations = request.user.consultations.select_related("doctor", "dependent")
    return render(request, "healthcare/consultations.html", {"consultations": consultations})


@login_required
def consultation_create(request):
    form = ConsultationForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        consultation = form.save(commit=False)
        consultation.user = request.user
        consultation.fee = consultation.doctor.consultation_fee
        if consultation.mode == Consultation.Mode.CLINIC:
            consultation.clinic_name = consultation.doctor.clinic_name
            consultation.clinic_address = consultation.doctor.clinic_address
            consultation.clinic_phone = consultation.doctor.phone
            if not consultation.clinic_name or not consultation.clinic_address:
                form.add_error("mode", "This doctor has not published a complete clinic address yet.")
                return render(request, "healthcare/form.html", {"form": form, "title": "Book a doctor consultation", "eyebrow": "Verified care"})
        if consultation.scheduled_at:
            availability = DoctorAvailability.objects.filter(
                doctor=consultation.doctor,
                weekday=consultation.scheduled_at.weekday(),
                start_time__lte=consultation.scheduled_at.time(),
                end_time__gt=consultation.scheduled_at.time(),
                is_active=True,
            ).first()
            if consultation.doctor.availability_slots.filter(is_active=True).exists() and not availability:
                form.add_error("scheduled_at", "Choose a time within the doctor's published availability.")
                return render(request, "healthcare/form.html", {"form": form, "title": "Book a doctor consultation", "eyebrow": "Verified care"})
            if availability and Consultation.objects.filter(
                doctor=consultation.doctor,
                scheduled_at=consultation.scheduled_at,
                status__in=[Consultation.Status.REQUESTED, Consultation.Status.CONFIRMED, Consultation.Status.IN_PROGRESS],
            ).count() >= availability.capacity:
                form.add_error("scheduled_at", "That consultation slot is full. Choose another time.")
                return render(request, "healthcare/form.html", {"form": form, "title": "Book a doctor consultation", "eyebrow": "Verified care"})
        consultation.save()
        ConsultationPayment.objects.create(consultation=consultation, amount=consultation.fee)
        create_notification(
            consultation.doctor.user,
            "New consultation request",
            f"{request.user.get_full_name() or request.user.username} requested a {consultation.get_mode_display().lower()} consultation. Review the request to confirm it.",
            Notification.NotificationType.GENERAL,
            reverse("healthcare:consultation_detail", args=[consultation.pk]),
        )
        create_notification(
            request.user,
            "Consultation request submitted",
            f"Your request with Dr. {consultation.doctor.full_name} is pending confirmation.",
            Notification.NotificationType.GENERAL,
            reverse("healthcare:consultation_detail", args=[consultation.pk]),
        )
        record_audit(request, "healthcare.consultation.created", consultation, "Consultation requested.")
        messages.success(request, "Consultation request submitted. The verified doctor will confirm it.")
        return redirect("healthcare:consultations")
    return render(request, "healthcare/form.html", {"form": form, "title": "Book a doctor consultation", "eyebrow": "Verified care"})


@login_required
def consultation_detail(request, pk):
    consultation = get_object_or_404(
        Consultation.objects.select_related("doctor", "dependent", "user"),
        Q(pk=pk) & (Q(user=request.user) | Q(doctor__user=request.user)),
    )
    form = ConsultationMessageForm(request.POST or None, request.FILES or None)
    followup_form = ConsultationFollowUpForm()
    if request.method == "POST" and form.is_valid():
        message = ConsultationMessage.objects.create(consultation=consultation, sender=request.user, message=form.cleaned_data["message"], attachment=form.cleaned_data.get("attachment"))
        record_audit(request, "healthcare.consultation.message", message, "Consultation message sent.")
        return redirect("healthcare:consultation_detail", pk=pk)
    payment = getattr(consultation, "payment", None)
    return render(request, "healthcare/consultation_detail.html", {"consultation": consultation, "form": form, "followup_form": followup_form, "can_pay": bool(payment and payment.status == ConsultationPayment.Status.PENDING), "is_doctor": consultation.doctor.user_id == request.user.id})


@login_required
def consultation_payment_start(request, pk):
    consultation = get_object_or_404(Consultation.objects.select_related("doctor"), pk=pk, user=request.user)
    payment = getattr(consultation, "payment", None)
    if payment and payment.status == ConsultationPayment.Status.PAID:
        return redirect("healthcare:consultation_detail", pk=pk)
    return render(request, "healthcare/consultation_payment.html", {"consultation": consultation, "payment": payment, "gateway_configured": consultation_payment_is_configured(), "razorpay_key_id": settings.RAZORPAY_KEY_ID})


@login_required
@require_POST
def consultation_payment_create(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk, user=request.user)
    try:
        payment, gateway_order = create_consultation_payment_order(consultation)
    except Exception:
        return JsonResponse({"ok": False, "error": "The consultation payment gateway is unavailable."}, status=503)
    return JsonResponse({"ok": True, "order_id": gateway_order.get("id"), "amount": int(payment.amount * 100), "currency": settings.RAZORPAY_CURRENCY})


@login_required
@require_POST
def consultation_payment_verify(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk, user=request.user)
    try:
        verify_consultation_payment(consultation, request.POST.get("razorpay_payment_id"), request.POST.get("razorpay_signature"))
    except Exception:
        messages.error(request, "Consultation payment verification failed.")
        return redirect("healthcare:consultation_payment_start", pk=pk)
    messages.success(request, "Consultation payment completed.")
    return redirect("healthcare:consultation_detail", pk=pk)


@login_required
def consultation_room(request, pk):
    consultation = get_object_or_404(Consultation.objects.select_related("doctor", "user"), pk=pk)
    if request.user.id not in {consultation.user_id, consultation.doctor.user_id}:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if consultation.mode == Consultation.Mode.CLINIC:
        messages.info(request, "This consultation is an in-clinic appointment. Use the clinic details on the consultation page.")
        return redirect("healthcare:consultation_detail", pk=pk)
    if consultation.status not in {Consultation.Status.CONFIRMED, Consultation.Status.IN_PROGRESS}:
        messages.info(request, "The consultation room becomes available after payment and confirmation.")
        return redirect("healthcare:consultation_detail", pk=pk)
    room_url = consultation_room_url(consultation)
    if room_url.startswith("http"):
        return redirect(room_url)
    return render(request, "healthcare/consultation_room.html", {"consultation": consultation, "room_id": consultation.room_id, "provider_configured": bool(getattr(settings, "CONSULTATION_ROOM_BASE_URL", ""))})


@login_required
@require_POST
def consultation_cancel(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk, user=request.user)
    payment = getattr(consultation, "payment", None)
    if consultation.status not in {Consultation.Status.REQUESTED, Consultation.Status.CONFIRMED}:
        messages.error(request, "This consultation can no longer be cancelled online.")
        return redirect("healthcare:consultation_detail", pk=pk)
    consultation.status = Consultation.Status.REFUND_PENDING if payment and payment.status == ConsultationPayment.Status.PAID else Consultation.Status.CANCELLED
    consultation.cancelled_at = timezone.now()
    consultation.save(update_fields=["status", "cancelled_at", "updated_at"])
    if payment and payment.status == ConsultationPayment.Status.PAID:
        payment.status = ConsultationPayment.Status.REFUND_PENDING
        payment.save(update_fields=["status", "updated_at"])
    create_notification(consultation.doctor.user, "Consultation cancelled", f"Consultation #{consultation.pk} was cancelled by the customer.", Notification.NotificationType.GENERAL, reverse("healthcare:consultations"))
    messages.success(request, "Consultation cancellation submitted.")
    return redirect("healthcare:consultations")


@login_required
@require_POST
def consultation_followup_create(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk, doctor__user=request.user)
    form = ConsultationFollowUpForm(request.POST)
    if form.is_valid():
        try:
            schedule_consultation_followup(consultation, request.user, form.cleaned_data["scheduled_at"], form.cleaned_data["notes"])
        except ValueError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Follow-up scheduled.")
    return redirect("healthcare:consultation_detail", pk=pk)


