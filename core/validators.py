from pathlib import Path

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


MAX_PRIVATE_DOCUMENT_SIZE = 10 * 1024 * 1024
MAX_PUBLIC_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


def _rewind(upload):
    try:
        upload.seek(0)
    except (AttributeError, OSError):
        pass


def validate_private_document(upload):
    if not upload:
        return
    if getattr(upload, "size", 0) > MAX_PRIVATE_DOCUMENT_SIZE:
        raise ValidationError("Document must be 10 MB or smaller.")

    extension = Path(upload.name).suffix.lower()
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError("Upload a PDF, JPG, PNG, or WEBP document.")

    _rewind(upload)
    header = upload.read(8)
    _rewind(upload)
    if extension == ".pdf":
        if not header.startswith(b"%PDF-"):
            raise ValidationError("The uploaded file is not a valid PDF document.")
        return

    try:
        image = Image.open(upload)
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("The uploaded file is not a valid image.") from exc
    finally:
        _rewind(upload)


def validate_public_image(upload):
    if not upload:
        return
    if getattr(upload, "size", 0) > MAX_PUBLIC_IMAGE_SIZE:
        raise ValidationError("Image must be 5 MB or smaller.")
    _rewind(upload)
    try:
        image = Image.open(upload)
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("Upload a valid image file.") from exc
    finally:
        _rewind(upload)
