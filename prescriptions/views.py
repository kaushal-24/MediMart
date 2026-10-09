from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from extras.models import Notification
from extras.services import create_notification

from .forms import PrescriptionUploadForm
from .models import Prescription


def user_has_approved_prescription(user, product=None, quantity=1):
    if not user.is_authenticated:
        return False
    prescriptions = user.prescriptions.filter(
        status=Prescription.Status.APPROVED,
        valid_until__gte=timezone.localdate(),
    ).prefetch_related("items")
    if product is None:
        return any(prescription.is_current for prescription in prescriptions)
    return any(
        prescription.authorizes(product, quantity)
        for prescription in prescriptions
    )


@login_required
def prescription_list(request):
    prescriptions = request.user.prescriptions.all()
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
            create_notification(
                request.user,
                "Prescription uploaded",
                "Your prescription was uploaded and is pending review.",
                Notification.NotificationType.PRESCRIPTION,
                prescription.get_absolute_url() if hasattr(prescription, "get_absolute_url") else "",
            )
            messages.success(
                request,
                "Prescription uploaded successfully and is pending review.",
            )
            return redirect("prescriptions:prescription_list")
    else:
        form = PrescriptionUploadForm()

    return render(request, "prescriptions/prescription_upload.html", {"form": form})


@login_required
def prescription_detail(request, pk):
    prescription = get_object_or_404(Prescription, pk=pk, user=request.user)
    return render(
        request,
        "prescriptions/prescription_detail.html",
        {"prescription": prescription},
    )
