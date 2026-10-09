import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


ENCRYPTED_PREFIX = "enc::"


def _fernet():
    configured = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if configured:
        key = configured.encode("ascii")
    else:
        digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


class EncryptedCharField(models.CharField):
    description = "Application-encrypted text"

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        if not value or not isinstance(value, str) or not value.startswith(ENCRYPTED_PREFIX):
            return value
        try:
            return _fernet().decrypt(value[len(ENCRYPTED_PREFIX) :].encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            return ""

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value or value.startswith(ENCRYPTED_PREFIX):
            return value
        token = _fernet().encrypt(value.encode("utf-8")).decode("ascii")
        return f"{ENCRYPTED_PREFIX}{token}"
