document.addEventListener("DOMContentLoaded", () => {
    const root = document.querySelector("[data-chatbot]");
    if (!root) return;
    const toggle = root.querySelector("[data-chatbot-toggle]");
    const close = root.querySelector("[data-chatbot-close]");
    const panel = root.querySelector("[data-chatbot-panel]");
    const form = root.querySelector("[data-chatbot-form]");
    const quickActions = root.querySelectorAll("[data-chatbot-quick-action]");
    const feedbackEndpoint = root.dataset.feedbackEndpoint || "";
    const input = root.querySelector("#medimartChatbotInput");
    const messages = root.querySelector("[data-chatbot-messages]");
    const csrf = form.querySelector("input[name='csrfmiddlewaretoken']")?.value || "";
    const reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const responseCache = new Map();
    const pendingRequests = new Map();
    const normalizeMessage = (message) => String(message).replace(/\s+/g, " ").trim().toLowerCase();
    const rememberResponse = (key, response) => {
        responseCache.set(key, response);
        if (responseCache.size > 20) {
            responseCache.delete(responseCache.keys().next().value);
        }
    };

    const splitPipeRow = (line) => String(line).trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((value) => value.trim());
    const resolveInternalUrl = (value) => {
        try {
            const url = new URL(String(value || "").trim(), window.location.origin);
            return url.origin === window.location.origin ? url.href : "";
        } catch {
            return "";
        }
    };
    const extractTableLink = (value) => {
        const markdown = String(value || "").match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        const url = resolveInternalUrl(markdown ? markdown[2] : value);
        return url ? {label: markdown ? markdown[1] : "Open product", url} : null;
    };
    const titleFromProductUrl = (url) => {
        try {
            const lastPart = new URL(url, window.location.origin).pathname.split("/").filter(Boolean).pop() || "Product result";
            return decodeURIComponent(lastPart).replace(/[-_]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
        } catch {
            return "Product result";
        }
    };
    const parseCatalogTable = (text) => {
        const lines = String(text).split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
        const headerIndex = lines.findIndex((line, index) => (
            line.includes("|") && lines[index + 1] && /^\|?\s*:?-{3,}.*\|/.test(lines[index + 1])
        ));
        if (headerIndex < 0) return null;
        const headers = splitPipeRow(lines[headerIndex]).map((header) => header.toLowerCase());
        const separatorIndex = headerIndex + 1;
        const rows = [];
        for (const line of lines.slice(separatorIndex + 1)) {
            if (!line.includes("|")) break;
            const columns = splitPipeRow(line);
            if (columns.length >= headers.length) rows.push(columns);
        }
        const categoryIndex = headers.findIndex((header) => header.includes("category"));
        const priceIndex = headers.findIndex((header) => header.includes("price"));
        const linkIndex = headers.findIndex((header) => header.includes("product page") || header.includes("link"));
        if (!rows.length || categoryIndex < 0 || priceIndex < 0 || linkIndex < 0) return null;
        return {intro: lines.slice(0, headerIndex).join(" "), categoryIndex, priceIndex, linkIndex, rows};
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

    const appendAssistantMessage = async (text, links = [], source = "local") => {
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

        const appendCatalogTable = () => {
            const table = parseCatalogTable(text);
            if (!table) return false;
            const resultList = document.createElement("div");
            resultList.className = "medimart-chatbot-result-list";
            if (table.intro) {
                const intro = document.createElement("p");
                intro.className = "medimart-chatbot-result-intro";
                intro.textContent = table.intro;
                resultList.appendChild(intro);
            }
            let rendered = 0;
            table.rows.forEach((columns, index) => {
                const resultUrl = extractTableLink(columns[table.linkIndex]);
                if (!resultUrl) return;
                const card = document.createElement("article");
                card.className = "medimart-chatbot-result";

                const heading = document.createElement("div");
                heading.className = "medimart-chatbot-result-heading";
                const number = document.createElement("span");
                number.className = "medimart-chatbot-result-number";
                number.textContent = String(index + 1).padStart(2, "0");
                const title = document.createElement("strong");
                title.textContent = resultUrl.label.startsWith("/") ? titleFromProductUrl(resultUrl.url) : resultUrl.label;
                heading.append(number, title);
                card.appendChild(heading);

                const details = document.createElement("div");
                details.className = "medimart-chatbot-result-details";
                const category = document.createElement("span");
                category.textContent = columns[table.categoryIndex];
                const price = document.createElement("strong");
                price.textContent = columns[table.priceIndex].replace(/₹?\s*/, "₹");
                details.append(category, price);
                card.appendChild(details);

                const link = document.createElement("a");
                link.className = "medimart-chatbot-result-link";
                link.href = resultUrl.url;
                link.textContent = "Open product";
                link.setAttribute("aria-label", `Open ${title.textContent}`);
                card.appendChild(link);
                resultList.appendChild(card);
                rendered += 1;
            });
            if (!rendered) return false;
            element.appendChild(resultList);
            return true;
        };

        const appendLinks = () => {
            const safeLinks = (Array.isArray(links) ? links : []).filter((item) => {
                try { return item?.url && new URL(item.url, window.location.origin).origin === window.location.origin; } catch { return false; }
            });
            if (!safeLinks.length) return;
            const list = document.createElement("div");
            list.className = "medimart-chatbot-links";
            safeLinks.forEach((item) => {
                const link = document.createElement("a");
                link.className = "medimart-chatbot-link";
                link.href = new URL(item.url, window.location.origin).href;
                const copy = document.createElement("span");
                copy.className = "medimart-chatbot-link-copy";
                const label = document.createElement("strong");
                label.textContent = item.label || "Open result";
                copy.appendChild(label);
                if (item.meta) {
                    const meta = document.createElement("small");
                    meta.textContent = item.meta;
                    copy.appendChild(meta);
                }
                link.appendChild(copy);
                const icon = document.createElement("i");
                icon.className = "bi bi-arrow-up-right";
                icon.setAttribute("aria-hidden", "true");
                link.appendChild(icon);
                link.title = item.meta || "Open MediMart result";
                list.appendChild(link);
            });
            element.appendChild(list);
        };
        const appendFeedback = () => {
            if (!feedbackEndpoint) return;
            const feedback = document.createElement("div");
            feedback.className = "medimart-chatbot-feedback";
            const prompt = document.createElement("span");
            prompt.textContent = "Was this helpful?";
            feedback.appendChild(prompt);
            [[true, "Yes"], [false, "No"]].forEach(([helpful, label]) => {
                const button = document.createElement("button");
                button.type = "button";
                button.textContent = label;
                button.setAttribute("aria-label", `${label}, this answer was helpful`);
                button.addEventListener("click", async () => {
                    feedback.querySelectorAll("button").forEach((item) => { item.disabled = true; });
                    try {
                        await fetch(feedbackEndpoint, {
                            method: "POST",
                            headers: {"Content-Type": "application/json", "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest"},
                            credentials: "same-origin",
                            body: JSON.stringify({helpful, source}),
                        });
                        prompt.textContent = "Thanks for the feedback.";
                    } catch {
                        feedback.querySelectorAll("button").forEach((item) => { item.disabled = false; });
                    }
                });
                feedback.appendChild(button);
            });
            element.appendChild(feedback);
        };
        if (reducedMotion) {
            if (!appendCatalogTable()) {
                element.textContent = text;
                appendLinks();
            }
            appendFeedback();
            messages.scrollTop = messages.scrollHeight;
            return;
        }

        if (appendCatalogTable()) {
            appendFeedback();
            messages.scrollTop = messages.scrollHeight;
            return;
        }

        const words = String(text).match(/\S+\s*/g) || [String(text)];
        for (const word of words) {
            element.textContent += word;
            messages.scrollTop = messages.scrollHeight;
            await wait(Math.min(42, Math.max(12, word.length * 3)));
        }
        appendLinks();
        appendFeedback();
    };

    toggle.addEventListener("click", () => setOpen(panel.hidden));
    close.addEventListener("click", () => setOpen(false));
    quickActions.forEach((action) => {
        action.addEventListener("click", () => {
            input.value = action.dataset.chatbotQuickAction || "";
            form.requestSubmit();
        });
    });
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
                const cached = responseCache.get(cacheKey);
                await appendAssistantMessage(cached.answer, cached.links, cached.source);
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
                        return {answer: data.answer, links: data.links || [], source: data.source || "local"};
                    }).finally(() => {
                        window.clearTimeout(timeout);
                        pendingRequests.delete(cacheKey);
                    });
                    pendingRequests.set(cacheKey, request);
                }
                const answer = await request;
                rememberResponse(cacheKey, answer);
                await appendAssistantMessage(answer.answer, answer.links, answer.source);
            }
        } catch (error) {
            await appendAssistantMessage(error.name === "AbortError" ? "The assistant took too long to respond. Please try again." : (error.message || "Assistant is temporarily unavailable."));
        } finally {
            input.disabled = false;
            input.focus();
        }
    });
});
