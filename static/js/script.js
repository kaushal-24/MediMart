document.addEventListener("DOMContentLoaded", () => {
    const markRequiredFields = (root = document) => {
        root.querySelectorAll("label[for]").forEach((label) => {
            const control = document.getElementById(label.htmlFor);
            if (!control || !control.required || label.querySelector(".required-indicator")) return;

            label.classList.add("is-required");
            const marker = document.createElement("span");
            marker.className = "required-indicator";
            marker.setAttribute("aria-hidden", "true");
            marker.title = "Required field";
            marker.setAttribute("data-bs-toggle", "tooltip");
            marker.setAttribute("data-bs-placement", "top");
            marker.textContent = "*";
            label.appendChild(marker);
        });
    };

    markRequiredFields();

    if ("MutationObserver" in window) {
        const formObserver = new MutationObserver(() => markRequiredFields());
        formObserver.observe(document.body, { childList: true, subtree: true });
    }

    const splash = document.querySelector("#siteSplash");
    if (splash) {
        if (document.documentElement.classList.contains("splash-seen")) {
            splash.remove();
        } else {
            window.setTimeout(() => splash.classList.add("is-hidden"), 520);
            window.setTimeout(() => splash.remove(), 1050);
        }
    }

    const utilityBar = document.querySelector("[data-utility-bar]");
    const utilityDismiss = utilityBar?.querySelector("[data-utility-dismiss]");
    if (utilityBar && utilityDismiss) {
        try {
            if (sessionStorage.getItem("medimart-utility-bar-dismissed") === "1") {
                utilityBar.remove();
            } else {
                utilityDismiss.addEventListener("click", () => {
                    utilityBar.classList.add("is-dismissed");
                    window.setTimeout(() => utilityBar.remove(), 180);
                    try {
                        sessionStorage.setItem("medimart-utility-bar-dismissed", "1");
                    } catch (storageError) {
                        // Dismissal still works for this page when browser storage is blocked.
                    }
                });
            }
        } catch (error) {
            utilityDismiss.addEventListener("click", () => utilityBar.remove());
        }
    }

    document.addEventListener("click", (event) => {
        const toggle = event.target.closest("[data-password-toggle]");
        if (!toggle) return;
        const input = document.getElementById(toggle.dataset.passwordToggle);
        if (!input) return;
        const showing = input.type === "password";
        input.type = showing ? "text" : "password";
        toggle.setAttribute("aria-pressed", String(showing));
        toggle.setAttribute("aria-label", showing ? "Hide password" : "Show password");
        toggle.setAttribute("title", showing ? "Hide password" : "Show password");
        toggle.innerHTML = `<i class="bi ${showing ? "bi-eye-slash" : "bi-eye"}" aria-hidden="true"></i>`;
    });

    document.querySelectorAll("[data-notification-toast]").forEach((toast) => {
        const dismiss = toast.querySelector("[data-notification-dismiss]");
        const countdown = toast.querySelector("[data-notification-countdown]");
        let remaining = Number.parseInt(countdown?.dataset.notificationCountdown || "24", 10);
        let countdownTimer;
        const remove = () => {
            if (countdownTimer) {
                window.clearInterval(countdownTimer);
            }
            toast.classList.add("is-leaving");
            window.setTimeout(() => toast.remove(), 240);
        };
        dismiss?.addEventListener("click", remove);
        countdownTimer = window.setInterval(() => {
            remaining -= 1;
            if (countdown) {
                countdown.textContent = `${Math.max(remaining, 0)}s`;
            }
            if (remaining <= 0) {
                window.clearInterval(countdownTimer);
                remove();
            }
        }, 1000);
    });

    const motionPreference = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : { matches: false };
    if (!motionPreference.matches) {
        document.documentElement.classList.add("js-reveal");
        const revealElements = document.querySelectorAll("[data-reveal]");
        if ("IntersectionObserver" in window) {
            const revealObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) return;
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                });
            }, { threshold: 0.08, rootMargin: "0px 0px -24px" });
            revealElements.forEach((element) => revealObserver.observe(element));
        } else {
            revealElements.forEach((element) => element.classList.add("is-visible"));
        }
    }

    const searchInput = document.querySelector("#siteSearchInput");
    const suggestionsPanel = document.querySelector("#searchSuggestions");
    const themeToggle = document.querySelector("#themeToggle");
    const detectLocationButton = document.querySelector("#detectLocationButton");
    const manualLocationForm = document.querySelector("#manualLocationForm");
    const locationStatus = document.querySelector("#locationStatus");
    const locationAttribution = document.querySelector("#locationAttribution");
    const addressLocationButton = document.querySelector("#addressLocationButton");
    const addressLocationStatus = document.querySelector("#addressLocationStatus");

    const setTheme = (theme) => {
        document.documentElement.setAttribute("data-bs-theme", theme);
        document.documentElement.setAttribute("data-theme", theme);
        try {
            localStorage.setItem("medimart-theme", theme);
        } catch (error) {
            // Theme still works for the current page if browser storage is unavailable.
        }

        if (!themeToggle) {
            return;
        }

        const isDark = theme === "dark";
        themeToggle.setAttribute("aria-pressed", String(isDark));
        themeToggle.setAttribute("aria-label", isDark ? "Switch to light theme" : "Switch to dark theme");
        themeToggle.setAttribute("title", isDark ? "Switch to light theme" : "Switch to dark theme");
        themeToggle.querySelector("i").className = isDark ? "bi bi-sun" : "bi bi-moon-stars";
    };

    const currentTheme = document.documentElement.getAttribute("data-bs-theme") || "light";
    setTheme(currentTheme);

    if (themeToggle) {
        themeToggle.addEventListener("click", () => {
            const nextTheme = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
            setTheme(nextTheme);
        });
    }

    const getCsrfToken = () => {
        const tokenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (tokenInput) {
            return tokenInput.value;
        }
        const cookie = document.cookie.split(";").map((item) => item.trim()).find((item) => item.startsWith("csrftoken="));
        return cookie ? decodeURIComponent(cookie.split("=").slice(1).join("=")) : "";
    };

    const setStatus = (element, message, type = "muted") => {
        if (!element) {
            return;
        }
        element.className = `small mt-3 text-${type}`;
        element.textContent = message;
    };

    const updateNavigationCounts = (data) => {
        [["[data-cart-count]", data.cart_item_count], ["[data-saved-count]", data.saved_item_count]].forEach(([selector, count]) => {
            document.querySelectorAll(selector).forEach((element) => {
                const value = Number(count || 0);
                element.textContent = value;
                element.classList.toggle("d-none", value < 1);
            });
        });
    };

    const showToast = (message, level = "success") => {
        const region = document.querySelector("#siteToastRegion");
        if (!region || !message) return;
        const toast = document.createElement("div");
        toast.className = `site-toast is-${level} p-3 small`;
        toast.setAttribute("role", level === "danger" ? "alert" : "status");
        toast.textContent = message;
        region.appendChild(toast);
        window.setTimeout(() => toast.remove(), 4200);
    };

    const setButtonBusy = (button, busy) => {
        if (!button) return;
        if (busy) {
            button.dataset.originalHtml = button.innerHTML;
            button.disabled = true;
            button.setAttribute("aria-busy", "true");
            button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Updating';
        } else {
            button.disabled = false;
            button.removeAttribute("aria-busy");
            if (button.dataset.originalHtml) button.innerHTML = button.dataset.originalHtml;
        }
    };

    const syncQuantitySteppers = (root = document) => {
        root.querySelectorAll("[data-quantity-stepper]").forEach((stepper) => {
            const input = stepper.querySelector("[data-cart-quantity]");
            const decrement = stepper.querySelector('[data-quantity-action="decrement"]');
            if (input && decrement) {
                decrement.disabled = Number(input.value || 1) <= 1;
            }
        });
    };

    syncQuantitySteppers();

    const submitQuantityForm = (input) => {
        const form = input.closest("form");
        if (!form) return;
        if (typeof form.requestSubmit === "function") {
            form.requestSubmit();
        } else {
            form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
        }
    };

    document.addEventListener("click", (event) => {
        const button = event.target.closest("[data-quantity-action]");
        if (!button || button.disabled) return;
        const stepper = button.closest("[data-quantity-stepper]");
        const input = stepper && stepper.querySelector("[data-cart-quantity]");
        if (!input) return;
        const delta = button.dataset.quantityAction === "increment" ? 1 : -1;
        input.value = Math.max(1, Number(input.value || 1) + delta);
        syncQuantitySteppers(stepper.parentElement);
        submitQuantityForm(input);
    });

    document.addEventListener("change", (event) => {
        const input = event.target.closest("[data-cart-quantity]");
        if (!input) return;
        input.value = Math.max(1, Number(input.value || 1));
        syncQuantitySteppers(input.closest("[data-quantity-stepper]").parentElement);
        submitQuantityForm(input);
    });

    const parseJsonResponse = async (response) => {
        const contentType = response.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
            window.location.href = response.url;
            return null;
        }
        return response.json();
    };

    document.addEventListener("submit", async (event) => {
        const form = event.target.closest("form[data-cart-coupon-form]");
        if (!form) return;
        event.preventDefault();
        const button = event.submitter || form.querySelector('button[type="submit"]');
        const params = new URLSearchParams(new FormData(form));
        if (event.submitter && event.submitter.name) {
            params.set(event.submitter.name, event.submitter.value);
        }
        setButtonBusy(button, true);
        try {
            const response = await fetch(`${form.action}?${params.toString()}`, {
                method: "GET",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                },
                credentials: "same-origin",
            });
            const data = await parseJsonResponse(response);
            if (!data) return;
            if (data.html) {
                const cartContent = document.querySelector("[data-cart-content]");
                if (cartContent) {
                    cartContent.innerHTML = data.html;
                    syncQuantitySteppers(cartContent);
                }
            }
            updateNavigationCounts(data);
            showToast(data.message, data.level || (response.ok ? "success" : "danger"));
        } catch (error) {
            showToast(error.message || "The coupon could not be checked.", "danger");
        } finally {
            setButtonBusy(button, false);
        }
    });

    document.addEventListener("submit", async (event) => {
        const form = event.target.closest("form[data-ajax-form], form[data-cart-action]");
        if (!form) return;
        event.preventDefault();
        const button = form.querySelector('button[type="submit"]');
        let completed = false;
        setButtonBusy(button, true);
        try {
            const response = await fetch(form.action, {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrfToken(),
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                },
                credentials: "same-origin",
                body: new FormData(form),
            });
            const data = await parseJsonResponse(response);
            if (!data) return;
            if (!response.ok || !data.ok) {
                if (data.redirect_url) window.location.href = data.redirect_url;
                throw new Error(data.message || data.error || "The update could not be completed.");
            }
            updateNavigationCounts(data);
            if (data.html) {
                const cartContent = document.querySelector("[data-cart-content]");
                if (cartContent) {
                    cartContent.innerHTML = data.html;
                    syncQuantitySteppers(cartContent);
                }
            }
            showToast(data.message, data.level || "success");
            if (data.redirect_url && form.matches('[data-ajax-form="quick-reorder"]')) {
                completed = true;
                window.setTimeout(() => { window.location.href = data.redirect_url; }, 350);
                return;
            }
            if (form.matches('[data-ajax-form="wishlist"]') && button) {
                button.innerHTML = '<i class="bi bi-check2 me-1"></i>Saved';
            }
            completed = true;
        } catch (error) {
            showToast(error.message || "The update could not be completed.", "danger");
        } finally {
            if (completed && form.matches('[data-ajax-form="wishlist"]') && button) {
                button.disabled = false;
                button.removeAttribute("aria-busy");
            } else {
                setButtonBusy(button, false);
            }
        }
    });

    const updateLocationLabels = (location) => {
        document.querySelectorAll("[data-site-location-label]").forEach((element) => {
            element.textContent = location.label || "Current location";
        });
        if (locationAttribution && location.attribution) {
            locationAttribution.textContent = location.attribution;
            locationAttribution.classList.remove("d-none");
        }
    };

    const fillAddressFromLocation = (location) => {
        const fieldMap = {
            "#id_address_line_1": location.address_line_1,
            "#id_house_number": location.house_number,
            "#id_road": location.road,
            "#id_neighbourhood": location.neighbourhood,
            "#id_suburb": location.suburb,
            "#id_locality": location.locality,
            "#id_subdistrict": location.subdistrict,
            "#id_district": location.district,
            "#id_city": location.city,
            "#id_state": location.state,
            "#id_pincode": location.pincode,
            "#id_country": location.country,
            "#id_country_code": location.country_code,
            "#id_latitude": location.latitude,
            "#id_longitude": location.longitude,
            "#id_geocoding_place_id": location.place_id,
            "#id_geocoding_osm_type": location.osm_type,
            "#id_geocoding_osm_id": location.osm_id,
            "#id_geocoding_display_name": location.display_name,
            "#id_geocoding_payload": JSON.stringify(location.raw_payload || {}),
            "#id_location_source": "geolocation",
        };
        Object.entries(fieldMap).forEach(([selector, value]) => {
            const field = document.querySelector(selector);
            if (field && value !== undefined && value !== null && value !== "") {
                field.value = value;
            }
        });
    };

    const postDetectedLocation = async (endpoint, coordinates) => {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: JSON.stringify(coordinates),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.error || "Location could not be selected.");
        }
        return data;
    };

    const detectLocation = (button, statusElement, onSuccess) => {
        if (!navigator.geolocation) {
            setStatus(statusElement, "Location detection is not supported by this browser.", "danger");
            return;
        }
        const originalHtml = button.innerHTML;
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Finding your location';
        setStatus(statusElement, "Waiting for browser permission...", "secondary");

        navigator.geolocation.getCurrentPosition(
            async (position) => {
                try {
                    const data = await postDetectedLocation(button.dataset.endpoint, {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                        accuracy: position.coords.accuracy,
                    });
                    updateLocationLabels(data.location);
                    if (onSuccess) {
                        onSuccess(data.location);
                    }
                    setStatus(statusElement, data.warning || `Location selected: ${data.location.label}`, data.warning ? "warning" : "success");
                } catch (error) {
                    setStatus(statusElement, error.message, "danger");
                } finally {
                    button.disabled = false;
                    button.innerHTML = originalHtml;
                }
            },
            (error) => {
                const messages = {
                    1: "Location permission was not granted. You can enter your city and pincode manually.",
                    2: "Your location is currently unavailable. Please try again or enter it manually.",
                    3: "Location detection timed out. Please try again.",
                };
                setStatus(statusElement, messages[error.code] || "Location could not be detected.", "danger");
                button.disabled = false;
                button.innerHTML = originalHtml;
            },
            { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 },
        );
    };

    if (detectLocationButton) {
        detectLocationButton.addEventListener("click", () => detectLocation(detectLocationButton, locationStatus));
    }

    if (addressLocationButton) {
        addressLocationButton.addEventListener("click", () => {
            detectLocation(addressLocationButton, addressLocationStatus, (location) => {
                fillAddressFromLocation(location);
                if (!location.pincode) {
                    setStatus(addressLocationStatus, "Location found. Please confirm the street and enter the pincode manually.", "warning");
                }
            });
        });
    }

    if (manualLocationForm) {
        manualLocationForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const submitButton = manualLocationForm.querySelector('button[type="submit"]');
            submitButton.disabled = true;
            setStatus(locationStatus, "Saving your delivery location...", "secondary");
            try {
                const response = await fetch(manualLocationForm.action, {
                    method: "POST",
                    headers: { "X-Requested-With": "XMLHttpRequest" },
                    body: new FormData(manualLocationForm),
                });
                const data = await response.json();
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Location could not be saved.");
                }
                updateLocationLabels(data.location);
                setStatus(locationStatus, `Delivery location set to ${data.location.label}.`, "success");
                window.setTimeout(() => {
                    const modal = bootstrap.Modal.getInstance(document.querySelector("#locationModal"));
                    if (modal) {
                        modal.hide();
                    }
                }, 500);
            } catch (error) {
                setStatus(locationStatus, error.message, "danger");
            } finally {
                submitButton.disabled = false;
            }
        });
    }

    const loadCatalogResults = async (url, form = null) => {
        const results = document.querySelector("[data-catalog-results]");
        if (!results) return;
        results.setAttribute("aria-busy", "true");
        try {
            const response = await fetch(url, {
                headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
                credentials: "same-origin",
            });
            const data = await response.json();
            if (!response.ok || !data.ok) throw new Error(data.error || "Products could not be refreshed.");
            results.innerHTML = data.html;
            if (data.url) window.history.replaceState({}, "", data.url);
            if (form) {
                const filterQuery = new URLSearchParams(new FormData(form));
                const nextUrl = new URL(form.action, window.location.href);
                nextUrl.search = filterQuery.toString();
                window.history.replaceState({}, "", nextUrl);
            }
        } catch (error) {
            showToast(error.message || "Products could not be refreshed.", "danger");
        } finally {
            results.removeAttribute("aria-busy");
        }
    };

    document.addEventListener("submit", (event) => {
        const form = event.target.closest("form[data-ajax-filter]");
        if (!form) return;
        event.preventDefault();
        const query = new URLSearchParams(new FormData(form));
        loadCatalogResults(`${form.action}?${query.toString()}`, form);
    });

    document.addEventListener("click", (event) => {
        const link = event.target.closest("[data-ajax-pagination] a");
        if (!link || !document.querySelector("[data-catalog-results]")) return;
        event.preventDefault();
        loadCatalogResults(link.href);
    });

    document.addEventListener("click", (event) => {
        const jumpButton = event.target.closest("[data-pagination-jump]");
        if (jumpButton) {
            const pagination = jumpButton.closest(".medimart-pagination");
            const dialog = pagination?.parentElement.querySelector("[data-pagination-jump-dialog]");
            const input = dialog?.querySelector("input[name='page']");
            if (!dialog || !input) return;
            input.max = jumpButton.dataset.paginationMax || input.max;
            input.value = "";
            input.setCustomValidity("");
            if (typeof dialog.showModal === "function") {
                dialog.showModal();
            } else {
                dialog.setAttribute("open", "");
            }
            window.setTimeout(() => input.focus(), 0);
            return;
        }

        const closeButton = event.target.closest("[data-pagination-jump-close]");
        if (closeButton) {
            const dialog = closeButton.closest("[data-pagination-jump-dialog]");
            if (dialog?.open) dialog.close();
        }
    });

    document.addEventListener("click", (event) => {
        const dialog = event.target.closest("[data-pagination-jump-dialog]");
        if (dialog && event.target === dialog) dialog.close();
    });

    document.addEventListener("submit", (event) => {
        const form = event.target.closest("[data-pagination-jump-form]");
        if (!form) return;
        event.preventDefault();
        const input = form.querySelector("input[name='page']");
        const page = Number.parseInt(input?.value || "", 10);
        const maxPage = Number.parseInt(input?.max || "", 10);
        if (!input || !Number.isInteger(page) || page < 1 || page > maxPage) {
            input?.setCustomValidity(`Enter a page number from 1 to ${maxPage}.`);
            input?.reportValidity();
            return;
        }
        input.setCustomValidity("");
        const dialog = form.closest("[data-pagination-jump-dialog]");
        if (dialog?.open) dialog.close();
        const destination = `${form.dataset.paginationUrl}${page}`;
        if (document.querySelector("[data-catalog-results]")) {
            loadCatalogResults(destination);
        } else {
            window.location.assign(destination);
        }
    });

    const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
    }[char]));

    const renderAiSearchResults = (panel, input, data) => {
        const results = data.results || [];
        const labTests = data.lab_tests || [];
        const doctors = data.doctors || [];
        const articles = data.articles || [];
        const suggestions = data.suggestions || [];
        const heading = escapeHtml(data.understanding || "Relevant products");
        const resultMarkup = results.length
            ? results.map((item) => `
                <a class="search-suggestion-item search-ai-result" role="option" href="${escapeHtml(item.url)}">
                    <span>${escapeHtml(item.name)}</span>
                    <small>${escapeHtml(item.meta || "")}${item.price ? ` · ₹${escapeHtml(item.price)}` : ""}</small>
                </a>
            `).join("")
            : '<div class="search-ai-empty">No matching products yet. Try a brand, condition, or product type.</div>';
        const labMarkup = labTests.length
            ? labTests.map((item) => `
                <a class="search-suggestion-item search-ai-result" role="option" href="${escapeHtml(item.url)}">
                    <span><i class="bi bi-eyedropper me-2 text-success" aria-hidden="true"></i>${escapeHtml(item.name)}</span>
                    <small>${escapeHtml(item.meta || "")}${item.price ? ` · ₹${escapeHtml(item.price)}` : ""}</small>
                </a>
            `).join("")
            : '<div class="search-ai-empty">No matching lab tests found.</div>';
        const safetyNote = escapeHtml(data.safety_note || "Catalog matches are educational and are not a diagnosis or prescription.");
        const extraGroups = [["Verified doctors", doctors], ["Reviewed health guides", articles]
            ].filter(([, items]) => items.length).map(([label, items]) => `<div class="search-ai-section-label">${label}</div>${items.map((item) => `<a class="search-suggestion-item search-ai-result" role="option" href="${escapeHtml(item.url)}"><span>${escapeHtml(item.name)}</span><small>${escapeHtml(item.meta || "")}</small></a>`).join("")}`).join("");
        const suggestionMarkup = suggestions.length ? `<div class="search-ai-section-label">Did you mean</div>${suggestions.map((item) => `<span class="search-query-chip">${escapeHtml(item.name)}</span>`).join(" ")}` : "";
        panel.innerHTML = `<div class="search-ai-heading"><i class="bi bi-stars me-2" aria-hidden="true"></i>${heading}</div><div class="search-ai-section-label">Related products and medicines</div>${resultMarkup}<div class="search-ai-section-label">Suggested lab tests</div>${labMarkup}${extraGroups}${suggestionMarkup}<div class="search-ai-safety"><i class="bi bi-info-circle me-2" aria-hidden="true"></i>${safetyNote}</div>`;
        panel.classList.add("is-visible");
        input.setAttribute("aria-expanded", "true");
    };

    const clearAiSearchResults = (form) => {
        const panel = form.querySelector("[data-ai-search-results]");
        const input = form.querySelector('input[name="q"]');
        if (!panel || !input) return;
        panel.innerHTML = "";
        panel.classList.remove("is-visible");
        input.setAttribute("aria-expanded", "false");
    };

    const autocompleteState = new WeakMap();
    const renderAutocompleteResults = (panel, input, data) => {
        const results = data.results || [];
        const groups = [
            ["Products and medicines", results],
            ["Categories", data.categories || []],
            ["Brands", data.brands || []],
            ["Lab tests", data.lab_tests || []],
        ].filter(([, items]) => items.length);
        if (!groups.length) {
            panel.innerHTML = '<div class="search-ai-empty">No quick matches yet. Press enter to ask MediMart AI.</div>';
        } else {
            panel.innerHTML = groups.map(([label, items]) => `<div class="search-ai-section-label">${label}</div>${items.map((item) => `
                <a class="search-suggestion-item search-autocomplete-result" role="option" href="${escapeHtml(item.url)}">
                    <span><i class="bi ${item.type === "lab_test" ? "bi-eyedropper" : item.type === "category" ? "bi-grid" : item.type === "brand" ? "bi-award" : "bi-search"} me-2 text-success" aria-hidden="true"></i>${escapeHtml(item.name)}</span>
                    <small>${escapeHtml(item.meta || "")}</small>
                </a>`).join("")}`).join("") + '<div class="search-autocomplete-hint"><i class="bi bi-stars me-1" aria-hidden="true"></i>Press enter for AI results and suggested lab tests</div>';
        }
        panel.classList.add("is-visible");
        input.setAttribute("aria-expanded", "true");
    };

    const requestAutocomplete = async (form) => {
        const input = form.querySelector('input[name="q"]');
        const panel = form.querySelector("[data-ai-search-results]");
        const endpoint = form.dataset.suggestionEndpoint;
        if (!input || !panel || !endpoint) return;
        const state = autocompleteState.get(form);
        const query = input.value.trim();
        if (query.length < 2) {
            state.controller?.abort();
            state.controller = null;
            if (!state.recentLoaded) {
                state.recentLoaded = true;
                const recent = await fetch(endpoint, { headers: { "Accept": "application/json" } }).then((response) => response.json()).catch(() => ({}));
                state.recentData = recent;
            }
            if (input.value.trim() === query && (state.recentData?.recent_queries || []).length) {
                renderAutocompleteResults(panel, input, {
                    results: state.recentData.recent_queries.map((item) => ({ name: item, meta: "Recent search", type: "recent", url: `${form.dataset.aiEndpoint}?q=${encodeURIComponent(item)}` })),
                });
            } else if (input.value.trim() === query) {
                clearAiSearchResults(form);
            }
            return;
        }
        if (state.autocompleteCache.has(query)) {
            renderAutocompleteResults(panel, input, state.autocompleteCache.get(query));
            return;
        }
        state.controller?.abort();
        state.requestId += 1;
        const requestId = state.requestId;
        const controller = new AbortController();
        state.controller = controller;
        try {
            const response = await fetch(`${endpoint}?q=${encodeURIComponent(query)}`, {
                headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
                signal: controller.signal,
            });
            const data = await response.json();
            if (state.requestId !== requestId || input.value.trim() !== query) return;
            if (!response.ok) throw new Error("Search suggestions are unavailable.");
            state.autocompleteCache.set(query, data);
            renderAutocompleteResults(panel, input, data);
        } catch (error) {
            if (error.name !== "AbortError" && state.requestId === requestId) clearAiSearchResults(form);
        } finally {
            if (state.controller === controller) state.controller = null;
        }
    };

    document.querySelectorAll("[data-ai-search-form]").forEach((form) => {
        const input = form.querySelector('input[name="q"]');
        const panel = form.querySelector("[data-ai-search-results]");
        const submitButton = form.querySelector('button[type="submit"]');
        if (!input || !panel) return;
        autocompleteState.set(form, {
            timer: null,
            requestId: 0,
            searchRequestId: 0,
            controller: null,
            searchController: null,
            searchInFlightQuery: "",
            autocompleteCache: new Map(),
            searchCache: new Map(),
            recentLoaded: false,
            recentData: null,
        });

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const query = input.value.trim();
            const state = autocompleteState.get(form);
            state.requestId += 1;
            state.controller?.abort();
            if (query.length < 3) {
                panel.innerHTML = '<div class="search-ai-empty">Describe what you need, for example: <strong>blood pressure monitor</strong>.</div>';
                panel.classList.add("is-visible");
                input.setAttribute("aria-expanded", "true");
                return;
            }

            if (state.searchInFlightQuery === query) return;
            if (state.searchCache.has(query)) {
                renderAiSearchResults(panel, input, state.searchCache.get(query));
                return;
            }
            state.searchController?.abort();
            const searchController = new AbortController();
            state.searchController = searchController;
            state.searchInFlightQuery = query;
            state.searchRequestId += 1;
            const searchRequestId = state.searchRequestId;
            const searchTimeout = window.setTimeout(() => searchController.abort(), 30000);

            if (submitButton) {
                submitButton.disabled = true;
                submitButton.setAttribute("aria-busy", "true");
            }
            panel.innerHTML = '<div class="search-ai-loading"><span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Finding relevant products...</div>';
            panel.classList.add("is-visible");
            input.setAttribute("aria-expanded", "true");
            try {
                const response = await fetch(`${form.dataset.aiEndpoint}?q=${encodeURIComponent(query)}`, {
                    headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
                    signal: searchController.signal,
                });
                const data = await response.json();
                if (!response.ok || !data.ok) throw new Error(data.error || "AI search could not be completed.");
                if (state.searchRequestId !== searchRequestId) return;
                state.searchCache.set(query, data);
                renderAiSearchResults(panel, input, data);
            } catch (error) {
                if (error.name !== "AbortError" && state.searchRequestId === searchRequestId) {
                    panel.innerHTML = `<div class="search-ai-empty text-danger">${escapeHtml(error.message || "AI search could not be completed.")}</div>`;
                }
            } finally {
                window.clearTimeout(searchTimeout);
                if (state.searchController === searchController) state.searchController = null;
                if (state.searchRequestId === searchRequestId) state.searchInFlightQuery = "";
                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.removeAttribute("aria-busy");
                }
            }
        });

        input.addEventListener("input", () => {
            const state = autocompleteState.get(form);
            window.clearTimeout(state.timer);
            if (input.value.trim().length < 2) {
                clearAiSearchResults(form);
                return;
            }
            state.timer = window.setTimeout(() => requestAutocomplete(form), 220);
        });
    });

    document.addEventListener("click", (event) => {
        document.querySelectorAll("[data-ai-search-form]").forEach((form) => {
            if (event.target.closest("[data-ai-search-form]") !== form) clearAiSearchResults(form);
        });
    });
});
