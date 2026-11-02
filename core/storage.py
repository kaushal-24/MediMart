from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

@deconstructible
class PrivateMediaStorage(FileSystemStorage):
    """Filesystem storage outside the public media root."""

    def __init__(self):
        super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)


private_media_storage = PrivateMediaStorage()
