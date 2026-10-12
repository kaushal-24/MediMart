from pathlib import Path

from django.utils import timezone


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}


def scan_uploaded_prescription(prescription):
    """Run a private technical scan after upload.

    This intentionally does not OCR, diagnose, identify medicines, or send the
    private file to an AI provider. Clinical interpretation remains manual.
    """
    file = prescription.file
    flags = []
    try:
        name = Path(file.name or "").name
        extension = Path(name).suffix.casefold()
        file_size = file.size
        if extension not in SUPPORTED_EXTENSIONS:
            flags.append("Unsupported file extension.")
        if file_size > 5 * 1024 * 1024:
            flags.append("File exceeds the 5 MB upload limit.")

        file.seek(0)
        header = file.read(8)
        file.seek(0)
        if extension == ".pdf" and not header.startswith(b"%PDF"):
            flags.append("The PDF signature could not be verified.")
        if extension in {".jpg", ".jpeg", ".png"}:
            from PIL import Image

            with Image.open(file) as image:
                image.verify()
            file.seek(0)

        status = prescription.ScanStatus.NEEDS_REVIEW if flags else prescription.ScanStatus.COMPLETE
        summary = (
            "The file passed technical checks and is ready for manual clinical review. "
            "This scan does not read medicines, diagnose conditions, or approve a prescription."
            if not flags
            else "The file needs attention before clinical review: " + " ".join(flags)
        )
        prescription.scan_status = status
        prescription.scan_summary = summary
        prescription.scan_flags = flags
        prescription.scan_completed_at = timezone.now()
        prescription.save(update_fields=["scan_status", "scan_summary", "scan_flags", "scan_completed_at", "updated_at"])
        return status
    except Exception:
        prescription.scan_status = prescription.ScanStatus.FAILED
        prescription.scan_summary = "The technical scan could not be completed. A reviewer must inspect the uploaded file."
        prescription.scan_flags = ["Technical scan failed."]
        prescription.scan_completed_at = timezone.now()
        prescription.save(update_fields=["scan_status", "scan_summary", "scan_flags", "scan_completed_at", "updated_at"])
        return prescription.scan_status
