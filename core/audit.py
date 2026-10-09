from .models import AuditEvent


def record_audit(request, action, target, summary, metadata=None):
    actor = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip_address = (forwarded_for.split(",")[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR")) or None
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        target_type=target._meta.label_lower if target is not None else "system",
        target_id=str(getattr(target, "pk", "") or ""),
        summary=summary[:255],
        metadata=metadata or {},
        ip_address=ip_address,
    )
