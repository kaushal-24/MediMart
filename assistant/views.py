import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from core.throttling import rate_limit

from .services import answer_question


@require_POST
@rate_limit("assistant-chat", 20, 60, json_response=True)
def chat(request):
    try:
        if request.content_type == "application/json":
            payload = json.loads(request.body or "{}")
        else:
            payload = request.POST
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"ok": False, "error": "Invalid request body."}, status=400)

    question = str(payload.get("message", "")).strip()
    if not question:
        return JsonResponse({"ok": False, "error": "Please enter a message."}, status=400)
    if len(question) > 1000:
        return JsonResponse({"ok": False, "error": "Please keep your message under 1000 characters."}, status=400)

    result = answer_question(request.user if request.user.is_authenticated else None, question)
    return JsonResponse({"ok": True, **result})
