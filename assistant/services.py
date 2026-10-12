import json
import hashlib
import logging
import re
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse

from django.core.cache import cache
from django.conf import settings
from django.db.models import Q

from orders.models import Order
from products.models import Product
from healthcare.models import LabTest


logger = logging.getLogger(__name__)


_BLOCKED_QUESTION_PATTERNS = (
    "password",
    "one time password",
    "otp",
    "api key",
    "secret key",
    "credit card",
    "cvv",
    "bank account",
    "database dump",
    "all users",
    "private document",
    "prescription file",
    "medical record",
)
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")
_SECRET_PATTERN = re.compile(r"\b(?:rzp|sk|pk)_[A-Za-z0-9_-]+\b", re.IGNORECASE)

_HEALTHCARE_SEARCH_ALIASES = {
    "diabetes": ("glucose", "hba1c", "blood sugar", "glucometer"),
    "diabetic": ("glucose", "hba1c", "blood sugar", "glucometer"),
    "hypertension": ("blood pressure", "bp monitor", "sphygmomanometer"),
    "high blood pressure": ("blood pressure", "bp monitor", "sphygmomanometer"),
    "blood pressure": ("hypertension", "bp monitor", "sphygmomanometer"),
    "fever": ("thermometer", "temperature"),
    "cold": ("thermometer", "nasal", "cough"),
    "cough": ("cough", "thermometer"),
    "anemia": ("haemoglobin", "hemoglobin", "cbc", "iron"),
    "thyroid": ("thyroid", "tsh", "t3", "t4"),
    "heart": ("ecg", "blood pressure", "cholesterol"),
}

_MODEL_COOLDOWN_CACHE_PREFIX = "assistant:model-cooldown"
_AI_RESPONSE_CACHE_PREFIX = "assistant:response"
_AI_SEARCH_CACHE_PREFIX = "assistant:search-plan"
_AI_DEDUP_LOCK_PREFIX = "assistant:dedup"
_RETRYABLE_HTTP_CODES = {404, 408, 409, 429, 500, 502, 503, 504}
_QUOTA_ERROR_TERMS = ("quota", "rate limit", "rate_limit", "resource exhausted", "too many requests", "limit")


class _NoAvailableModelError(OSError):
    pass


def answer_question(user, question):
    question = " ".join((question or "").split())[: settings.CHATBOT_MAX_INPUT_CHARS]
    if not question:
        return {"answer": "Please ask a question about MediMart, products, orders, or healthcare services.", "source": "local"}

    lowered = question.casefold()
    if any(pattern in lowered for pattern in _BLOCKED_QUESTION_PATTERNS):
        return {
            "answer": "I cannot access or disclose passwords, payment credentials, private medical files, or other sensitive personal data.",
            "source": "policy",
        }

    private_answer = _answer_order_question(user, lowered)
    if private_answer:
        return {"answer": private_answer, "source": "local"}

    healthcare_answer = _answer_healthcare_question(user, lowered)
    if healthcare_answer:
        return {"answer": healthcare_answer, "source": "local"}

    response_cache_key = _assistant_cache_key(_AI_RESPONSE_CACHE_PREFIX, question)
    cached_result = cache.get(response_cache_key)
    if cached_result:
        return cached_result

    dedup_lock_key = _assistant_cache_key(_AI_DEDUP_LOCK_PREFIX, f"chat:{question}")
    if not cache.add(dedup_lock_key, True, timeout=_chatbot_dedup_lock_seconds()):
        # Another request is already asking the provider the same question. Do not
        # create a second provider call while the first response is in flight.
        return {
            "answer": "I am preparing that answer. Please try the same question again in a moment.",
            "source": "local",
        }

    context = _public_catalog_context(question)
    try:
        if settings.CHATBOT_API_URL and settings.CHATBOT_API_KEY:
            try:
                answer = _call_custom_ai(question, context)
                if answer:
                    result = {"answer": _redact_sensitive_output(answer), "source": "custom_ai"}
                    cache.set(response_cache_key, result, timeout=_chatbot_response_cache_seconds())
                    return result
            except (OSError, ValueError, urllib.error.URLError) as exc:
                logger.warning("AI assistant provider unavailable after model failover: %s", _provider_error_label(exc))

        result = {"answer": _local_fallback(question, context), "source": "local"}
        cache.set(response_cache_key, result, timeout=_chatbot_fallback_cache_seconds())
        return result
    finally:
        cache.delete(dedup_lock_key)


def ai_search_plan(question):
    """Turn natural language into safe product and lab-test terms.

    The AI only plans the search. Catalog and lab databases remain authoritative,
    and the result is never presented as a diagnosis or prescription.
    """
    normalized = " ".join((question or "").split())[: settings.CHATBOT_MAX_INPUT_CHARS]
    fallback_terms = _expand_healthcare_terms(normalized)
    plan = {
        "terms": fallback_terms,
        "lab_terms": fallback_terms,
        "intent": "catalog",
        "summary": f"Matching MediMart products for: {normalized}",
        "source": "local",
    }
    if len(normalized) < 3 or not settings.CHATBOT_API_URL or not settings.CHATBOT_API_KEY:
        return plan

    search_cache_key = _assistant_cache_key(_AI_SEARCH_CACHE_PREFIX, normalized)
    cached_plan = cache.get(search_cache_key)
    if cached_plan:
        return cached_plan

    dedup_lock_key = _assistant_cache_key(_AI_DEDUP_LOCK_PREFIX, f"search:{normalized}")
    if not cache.add(dedup_lock_key, True, timeout=_chatbot_dedup_lock_seconds()):
        return plan

    try:
        catalog = list(
            list(Product.objects.filter(is_active=True).values_list("name", "category__name", "product_type")[:80])
            + list(LabTest.objects.filter(is_active=True).values_list("name", "category", "partner__name")[:60])
        )
        raw = _call_custom_ai(
            (
                "Interpret the user's shopping request for a healthcare catalog. The request is: "
                f"{normalized}\n\nReturn only valid JSON with keys "
                "terms (an array of up to 6 short product/category search terms) and summary (a short human-readable "
                "understanding), lab_terms (up to 6 lab-test search terms), and intent (catalog, lab_tests, or both). "
                "A disease or symptom is a search context only. Do not diagnose, recommend a prescription, invent products, "
                "or include personal data. "
                f"Catalog labels: {json.dumps(catalog, ensure_ascii=True)}"
            ),
            [],
            system_instruction=(
                "You are MediMart's catalog search planner. Convert the user's shopping request into safe search "
                "terms that match the catalog labels included in the user message. Return only the requested JSON. "
                "A disease or symptom is search context, not a diagnosis or prescription. Never invent products, "
                "medical advice, or personal data."
            ),
        )
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            cache.set(search_cache_key, plan, timeout=_chatbot_search_cache_seconds())
            return plan
        parsed = json.loads(raw[start : end + 1])
        terms = [str(term).strip() for term in parsed.get("terms", []) if str(term).strip()][:6]
        lab_terms = [str(term).strip() for term in parsed.get("lab_terms", []) if str(term).strip()][:6]
        if terms and not _search_terms_match_context(terms, normalized):
            logger.warning("AI search returned off-topic terms; using healthcare aliases instead.")
            plan["summary"] = f"Matching MediMart products and tests for: {normalized}"
            plan["source"] = "local"
            cache.set(search_cache_key, plan, timeout=_chatbot_search_cache_seconds())
            return plan
        plan["source"] = "custom_ai"
        if terms:
            plan["terms"] = terms
        if lab_terms:
            plan["lab_terms"] = lab_terms
        if parsed.get("intent") in {"catalog", "lab_tests", "both"}:
            plan["intent"] = parsed["intent"]
        if parsed.get("summary"):
            plan["summary"] = str(parsed["summary"])[:180]
    except (OSError, ValueError, TypeError, urllib.error.URLError, json.JSONDecodeError) as exc:
        logger.warning("AI search provider unavailable after model failover: %s", _provider_error_label(exc))
    finally:
        cache.delete(dedup_lock_key)
    cache.set(search_cache_key, plan, timeout=_chatbot_search_cache_seconds())
    return plan


def _assistant_cache_key(prefix, value):
    digest = hashlib.sha256(str(value).casefold().encode("utf-8")).hexdigest()[:32]
    provider = str(getattr(settings, "CHATBOT_PROVIDER", "auto")).casefold()
    return f"{prefix}:{provider}:{digest}"


def _chatbot_response_cache_seconds():
    return max(0, int(getattr(settings, "CHATBOT_RESPONSE_CACHE_SECONDS", 300)))


def _chatbot_search_cache_seconds():
    return max(0, int(getattr(settings, "CHATBOT_SEARCH_CACHE_SECONDS", 180)))


def _chatbot_fallback_cache_seconds():
    return max(0, int(getattr(settings, "CHATBOT_FALLBACK_CACHE_SECONDS", 30)))


def _chatbot_dedup_lock_seconds():
    return max(5, int(getattr(settings, "CHATBOT_DEDUP_LOCK_SECONDS", 45)))


def _search_terms_match_context(terms, question):
    """Reject AI terms that drift away from a recognized healthcare context."""
    lowered_question = question.casefold()
    context_phrases = {
        phrase
        for phrase, aliases in _HEALTHCARE_SEARCH_ALIASES.items()
        if phrase in lowered_question
        for phrase in (phrase, *aliases)
    }
    if not context_phrases:
        return True
    return any(
        context_phrase in str(term).casefold()
        for term in terms
        for context_phrase in context_phrases
    )


def _expand_healthcare_terms(question):
    terms = [term for term in re.findall(r"[A-Za-z0-9]+", question.casefold()) if len(term) > 2][:8]
    lowered = question.casefold()
    for phrase, aliases in _HEALTHCARE_SEARCH_ALIASES.items():
        if phrase in lowered:
            terms.extend(aliases)
    unique = []
    for term in terms:
        if term not in unique:
            unique.append(term)
    return unique[:12]


def _answer_order_question(user, lowered_question):
    if user is None or not any(word in lowered_question for word in ("order", "delivery", "shipment", "payment")):
        return ""
    if "my" not in lowered_question and "order" not in lowered_question:
        return ""

    orders = list(
        Order.objects.filter(customer=user)
        .only("order_number", "order_status", "payment_status", "created_at")
        .order_by("-created_at")[:3]
    )
    if not orders:
        return "I could not find any orders on your MediMart account."
    if any(word in lowered_question for word in ("latest", "recent", "my order", "track", "delivery", "shipment")):
        latest = orders[0]
        return (
            f"Your latest order {latest.order_number} is {latest.get_order_status_display().lower()} "
            f"and its payment is {latest.get_payment_status_display().lower()}."
        )
    return "I can help with your latest order status. Please ask about tracking or delivery."


def _answer_healthcare_question(user, lowered_question):
    """Answer account-scoped healthcare questions without sending private data to AI."""
    if user is None:
        return ""

    from healthcare.models import Consultation, LabBooking

    lab_terms = ("lab", "test", "report", "diagnostic", "sample", "invoice")
    consultation_terms = ("consultation", "consult", "doctor", "appointment", "follow up", "follow-up")

    if any(term in lowered_question for term in lab_terms):
        booking = (
            LabBooking.objects.filter(user=user)
            .select_related("lab_test", "lab_test__partner", "invoice")
            .order_by("-created_at")
            .first()
        )
        if not booking:
            return "I could not find a lab booking on your MediMart account. You can browse available tests from the Lab tests section."
        status = booking.get_status_display().lower()
        details = f"Your latest lab booking is {booking.lab_test.name} with {booking.lab_test.partner.name}; its status is {status}."
        if booking.report_file or booking.status == LabBooking.Status.REPORT_READY:
            details += " Your report is ready to open securely from Health records or My lab bookings."
        elif booking.report_ready_at:
            details += " The report is being prepared; check My lab bookings for the latest update."
        if getattr(booking, "invoice", None):
            details += f" Invoice {booking.invoice.invoice_number} is {booking.invoice.get_status_display().lower()}."
        return details

    if any(term in lowered_question for term in consultation_terms):
        consultation = (
            Consultation.objects.filter(user=user)
            .select_related("doctor", "payment")
            .order_by("-created_at")
            .first()
        )
        if not consultation:
            return "I could not find a doctor consultation on your MediMart account."
        details = f"Your latest consultation with Dr. {consultation.doctor.full_name} is {consultation.get_status_display().lower()}"
        if consultation.scheduled_at:
            details += f" for {consultation.scheduled_at:%d %b %Y, %I:%M %p}"
        details += "."
        if getattr(consultation, "payment", None):
            details += f" Consultation payment is {consultation.payment.get_status_display().lower()}."
        if consultation.followup_until:
            details += f" Follow-up access is available until {consultation.followup_until:%d %b %Y}."
        details += " This assistant cannot diagnose or replace your doctor."
        return details

    return ""


def _public_catalog_context(question):
    terms = _expand_healthcare_terms(question)[:12]
    products = Product.objects.filter(is_active=True).select_related("category").only(
        "name", "description", "selling_price", "category__name"
    )
    if terms:
        query = Q()
        for term in terms:
            query |= Q(name__icontains=term) | Q(description__icontains=term) | Q(category__name__icontains=term)
        products = products.filter(query)
    rows = []
    for product in products.order_by("name")[:6]:
        rows.append(
            {
                "name": product.name,
                "type": "product",
                "category": product.category.name if product.category else "Healthcare",
                "price_inr": str(product.selling_price),
                "description": (product.description or "")[:240],
            }
        )
    lab_tests = LabTest.objects.filter(is_active=True).select_related("partner").only(
        "name",
        "description",
        "preparation",
        "category",
        "price",
        "partner__name",
    )
    if terms:
        lab_query = Q()
        for term in terms:
            lab_query |= (
                Q(name__icontains=term)
                | Q(description__icontains=term)
                | Q(preparation__icontains=term)
                | Q(partner__name__icontains=term)
            )
        lab_tests = lab_tests.filter(lab_query)
    for lab_test in lab_tests.order_by("name")[:6]:
        rows.append(
            {
                "name": lab_test.name,
                "type": "lab_test",
                "category": lab_test.get_category_display(),
                "price_inr": str(lab_test.price),
                "description": (lab_test.description or lab_test.preparation or "")[:240],
            }
        )
    return rows[:12]


def _call_custom_ai(question, context, *, system_instruction=None):
    system_instruction = system_instruction or (
        "You are MediMart's support assistant. Answer concisely and safely. "
        "Never request, reveal, infer, or invent passwords, OTPs, payment credentials, "
        "addresses, phone numbers, emails, medical records, prescriptions, API keys, or internal database details. "
        "Do not diagnose or replace a clinician. For emergencies, advise local emergency services. "
        "Use only the public catalog context supplied below; say when information is unavailable."
    )
    messages = [
        {
            "role": "system",
            "content": f"{system_instruction}\nPublic catalog context: {json.dumps(context, ensure_ascii=True)}",
        },
        {"role": "user", "content": question},
    ]
    provider = _provider_name()
    last_error = None
    attempted_model = False
    for model in _model_candidates():
        if _model_is_on_cooldown(provider, model):
            continue
        attempted_model = True
        try:
            if provider == "gemini":
                return _call_gemini(question, messages[0]["content"], model=model)
            return _call_openai_compatible(messages, model)
        except Exception as exc:
            if not _is_retryable_provider_error(exc):
                raise
            logger.warning(
                "AI model '%s' failed for provider '%s': %s",
                model,
                provider,
                _provider_error_label(exc),
            )
            _cool_down_model(provider, model)
            last_error = exc

    if last_error:
        raise last_error
    if attempted_model:
        raise _NoAvailableModelError("No configured AI model is available.")
    raise _NoAvailableModelError("All configured AI models are temporarily cooling down.")


def _call_openai_compatible(messages, model):
    endpoint = _openai_compatible_endpoint(settings.CHATBOT_API_URL)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": settings.CHATBOT_MAX_OUTPUT_TOKENS,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MediMart/1.0",
            **({"Authorization": f"Bearer {settings.CHATBOT_API_KEY}"} if settings.CHATBOT_API_KEY else {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=settings.CHATBOT_TIMEOUT_SECONDS) as response:
        if response.status < 200 or response.status >= 300:
            raise urllib.error.HTTPError(endpoint, response.status, "AI provider error", response.headers, None)
        data = json.loads(response.read().decode("utf-8"))
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Unsupported custom AI response format") from exc


def _call_gemini(question, system_instruction, *, model=None):
    model = model or settings.CHATBOT_MODEL
    if not model or model == "custom-model":
        model = "gemini-3.6-flash"
    generation_config = {
        "temperature": 0.2,
        "maxOutputTokens": settings.CHATBOT_MAX_OUTPUT_TOKENS,
    }
    if model.startswith("gemini-3.8"):
        generation_config["thinkingConfig"] = {"thinkingLevel": "low"}
    elif model.startswith("gemini-3"):
        generation_config["thinkingConfig"] = {"thinkingLevel": settings.CHATBOT_THINKING_LEVEL}
    elif model.startswith("gemini-2.5"):
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}
    endpoint = f"{settings.CHATBOT_API_URL.rstrip('/')}/models/{quote(model, safe='')}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": question}]}],
        "generationConfig": generation_config,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-goog-api-key": settings.CHATBOT_API_KEY,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=settings.CHATBOT_TIMEOUT_SECONDS) as response:
        if response.status < 200 or response.status >= 300:
            raise urllib.error.HTTPError(endpoint, response.status, "AI provider error", response.headers, None)
        data = json.loads(response.read().decode("utf-8"))
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(str(part.get("text", "")) for part in parts).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Unsupported Gemini response format") from exc


def _model_candidates():
    configured = getattr(settings, "CHATBOT_MODELS", []) or []
    primary = getattr(settings, "CHATBOT_MODEL", "")
    candidates = [primary, *configured]
    unique = []
    for model in candidates:
        model = str(model).strip()
        if model and model not in unique and model != "custom-model":
            unique.append(model)
    return unique or ["custom-model"]


def _model_cooldown_key(provider, model):
    return f"{_MODEL_COOLDOWN_CACHE_PREFIX}:{provider}:{model}"


def _model_is_on_cooldown(provider, model):
    return bool(cache.get(_model_cooldown_key(provider, model)))


def _cool_down_model(provider, model):
    cache.set(
        _model_cooldown_key(provider, model),
        True,
        timeout=max(1, int(getattr(settings, "CHATBOT_MODEL_COOLDOWN_SECONDS", 60))),
    )


def _is_retryable_provider_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code in _RETRYABLE_HTTP_CODES:
            return True
        if exc.code == 403:
            try:
                details = exc.read().decode("utf-8", errors="ignore").casefold()
            except (OSError, AttributeError):
                details = ""
            return any(term in details for term in _QUOTA_ERROR_TERMS)
        return False
    return isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, OSError))


def _provider_error_label(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code} ({exc.reason})"
    return f"{type(exc).__name__}: {exc}"


def _provider_name():
    configured = getattr(settings, "CHATBOT_PROVIDER", "auto").casefold()
    if configured != "auto":
        return configured
    hostname = urlparse(settings.CHATBOT_API_URL).hostname or ""
    return "gemini" if hostname == "generativelanguage.googleapis.com" else "openai_compatible"


def _openai_compatible_endpoint(url):
    normalized = url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _local_fallback(question, context):
    if context:
        names = ", ".join(item["name"] for item in context[:3])
        return f"I found these relevant MediMart products: {names}. Open a product page for availability and detailed information."
    return (
        "I can help with MediMart products, order status, delivery, prescriptions, and healthcare services. "
        "For medical advice, please consult a qualified clinician."
    )


def _redact_sensitive_output(value):
    value = _EMAIL_PATTERN.sub("[private email redacted]", value)
    value = _PHONE_PATTERN.sub("[private phone redacted]", value)
    return _SECRET_PATTERN.sub("[private credential redacted]", value)[: settings.CHATBOT_MAX_OUTPUT_CHARS]
