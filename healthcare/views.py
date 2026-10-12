from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.audit import record_audit
from accounts.models import UserProfile
from extras.models import DoctorProfile

from .forms import ConsultationForm, ConsultationMessageForm, DependentForm, HealthRecordForm, LabBookingForm, LabRescheduleForm, MedicationReminderForm
from .models import (
    Consultation,
    ConsultationMessage,
    ConsultationPayment,
    DoctorAvailability,
    HealthRecord,
    LabBooking,
    LabCollectionSlot,
    LabInvoice,
    LabSampleEvent,
    LabTest,
    MedicationReminder,
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
    if request.method == "POST" and form.is_valid():
        message = ConsultationMessage.objects.create(consultation=consultation, sender=request.user, message=form.cleaned_data["message"], attachment=form.cleaned_data.get("attachment"))
        record_audit(request, "healthcare.consultation.message", message, "Consultation message sent.")
        return redirect("healthcare:consultation_detail", pk=pk)
    return render(request, "healthcare/consultation_detail.html", {"consultation": consultation, "form": form})


