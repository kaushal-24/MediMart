from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


if settings.USE_CLOUD_MEDIA:
    from storages.backends.s3 import S3Storage

    @deconstructible
    class PrivateMediaStorage(S3Storage):
        """Private S3 storage for regulated user uploads."""

        def __init__(self):
            options = {
                "bucket_name": settings.MEDIA_CLOUD_BUCKET,
                "location": "private",
                "default_acl": None,
                "file_overwrite": False,
                "querystring_auth": True,
                "object_parameters": {"CacheControl": "private, no-store"},
            }
            options.update(settings.MEDIA_CLOUD_CONNECTION_OPTIONS)
            super().__init__(**options)
else:
    @deconstructible
    class PrivateMediaStorage(FileSystemStorage):
        """Filesystem storage outside the public media root."""

        def __init__(self):
            super().__init__(location=settings.PRIVATE_MEDIA_ROOT, base_url=None)


private_media_storage = PrivateMediaStorage()
