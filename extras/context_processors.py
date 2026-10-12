def in_app_notifications(request):
    if not request.user.is_authenticated:
        return {
            "unread_notification_count": 0,
            "latest_unread_notifications": [],
        }

    unread = request.user.notifications.filter(is_read=False)
    # Keep unread notifications in the account center, but do not replay the
    # same toast on every page request in the same browser session.
    if getattr(getattr(request, "resolver_match", None), "url_name", "") == "notification_list":
        return {
            "unread_notification_count": unread.count(),
            "latest_unread_notifications": [],
        }
    session_key = f"notification_toasts_seen_{request.user.pk}"
    seen_ids = set(request.session.get(session_key, []))
    candidates = list(unread.exclude(pk__in=seen_ids).order_by("-created_at")[:3])
    if candidates:
        seen_ids.update(notification.pk for notification in candidates)
        request.session[session_key] = list(seen_ids)[-200:]
        request.session.modified = True
    return {
        "unread_notification_count": unread.count(),
        "latest_unread_notifications": candidates,
    }
