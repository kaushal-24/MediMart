document.addEventListener("DOMContentLoaded", () => {
    const root = document.querySelector("[data-chatbot]");
    if (!root) return;
    const toggle = root.querySelector("[data-chatbot-toggle]");
    const close = root.querySelector("[data-chatbot-close]");
    const panel = root.querySelector("[data-chatbot-panel]");
    const form = root.querySelector("[data-chatbot-form]");
    const input = root.querySelector("#medimartChatbotInput");
    const messages = root.querySelector("[data-chatbot-messages]");
    const csrf = form.querySelector("input[name='csrfmiddlewaretoken']")?.value || "";
    const reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const responseCache = new Map();
    const pendingRequests = new Map();
    const normalizeMessage = (message) => String(message).replace(/\s+/g, " ").trim().toLowerCase();
    const rememberResponse = (key, answer) => {
        responseCache.set(key, answer);
        if (responseCache.size > 20) {
            responseCache.delete(responseCache.keys().next().value);
        }
    };

    const setOpen = (open) => {
        panel.hidden = !open;
        toggle.setAttribute("aria-expanded", String(open));
        if (open) input.focus();
    };
    const appendMessage = (text, role) => {
        const element = document.createElement("div");
        element.className = `medimart-chatbot-message is-${role}`;
        element.textContent = text;
        messages.appendChild(element);
        messages.scrollTop = messages.scrollHeight;
    };

    const wait = (duration) => new Promise((resolve) => window.setTimeout(resolve, duration));

    const appendAssistantMessage = async (text) => {
        const element = document.createElement("div");
        element.className = "medimart-chatbot-message is-assistant is-typing";
        element.setAttribute("role", "status");
        element.setAttribute("aria-label", "Assistant is typing");
        element.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
        messages.appendChild(element);
        messages.scrollTop = messages.scrollHeight;

        if (!reducedMotion) await wait(280);
        element.classList.remove("is-typing");
        element.removeAttribute("aria-label");
        element.removeAttribute("role");
        element.textContent = "";

        if (reducedMotion) {
            element.textContent = text;
            messages.scrollTop = messages.scrollHeight;
            return;
        }

        const words = String(text).match(/\S+\s*/g) || [String(text)];
        for (const word of words) {
            element.textContent += word;
            messages.scrollTop = messages.scrollHeight;
            await wait(Math.min(42, Math.max(12, word.length * 3)));
        }
    };

    toggle.addEventListener("click", () => setOpen(panel.hidden));
    close.addEventListener("click", () => setOpen(false));
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const message = input.value.trim();
        if (!message) return;
        appendMessage(message, "user");
        input.value = "";
        input.disabled = true;
        const cacheKey = normalizeMessage(message);
        try {
            if (responseCache.has(cacheKey)) {
                await appendAssistantMessage(responseCache.get(cacheKey));
            } else {
                let request = pendingRequests.get(cacheKey);
                if (!request) {
                    const controller = new AbortController();
                    const timeout = window.setTimeout(() => controller.abort(), 30000);
                    request = fetch(root.dataset.endpoint, {
                        method: "POST",
                        headers: {"Content-Type": "application/json", "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest"},
                        credentials: "same-origin",
                        signal: controller.signal,
                        body: JSON.stringify({message}),
                    }).then(async (response) => {
                        const data = await response.json();
                        if (!response.ok || !data.ok) throw new Error(data.error || "Assistant is temporarily unavailable.");
                        return data.answer;
                    }).finally(() => {
                        window.clearTimeout(timeout);
                        pendingRequests.delete(cacheKey);
                    });
                    pendingRequests.set(cacheKey, request);
                }
                const answer = await request;
                rememberResponse(cacheKey, answer);
                await appendAssistantMessage(answer);
            }
        } catch (error) {
            await appendAssistantMessage(error.name === "AbortError" ? "The assistant took too long to respond. Please try again." : (error.message || "Assistant is temporarily unavailable."));
        } finally {
            input.disabled = false;
            input.focus();
        }
    });
});
