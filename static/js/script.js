document.addEventListener("DOMContentLoaded", () => {
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
        themeToggle.innerHTML = isDark
            ? '<i class="bi bi-sun me-1"></i><span></span>'
            : '<i class="bi bi-moon-stars me-1"></i><span></span>';
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

    document.querySelectorAll("[data-license-lookup]").forEach((form) => {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const button = form.querySelector('button[type="submit"]');
            const resultElement = form.querySelector("[data-license-result]");
            const originalHtml = button.innerHTML;
            button.disabled = true;
            button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Checking';
            if (resultElement) {
                resultElement.className = "small ms-2 text-secondary";
                resultElement.textContent = "Contacting the configured registry...";
            }
            try {
                const response = await fetch(form.action, {
                    method: "POST",
                    headers: {"X-Requested-With": "XMLHttpRequest"},
                    body: new FormData(form),
                });
                const data = await response.json();
                if (!response.ok || !data.ok) {
                    throw new Error(data.error || "Licence lookup failed.");
                }
                if (resultElement) {
                    resultElement.className = `small ms-2 text-${data.matched ? "success" : "warning"}`;
                    resultElement.textContent = data.message;
                }
                if (data.available) {
                    window.setTimeout(() => window.location.reload(), 900);
                }
            } catch (error) {
                if (resultElement) {
                    resultElement.className = "small ms-2 text-danger";
                    resultElement.textContent = error.message;
                }
            } finally {
                button.disabled = false;
                button.innerHTML = originalHtml;
            }
        });
    });

    if (!searchInput) {
        return;
    }

    const clearSuggestions = () => {
        if (suggestionsPanel) {
            suggestionsPanel.innerHTML = "";
            suggestionsPanel.classList.remove("is-visible");
            searchInput.setAttribute("aria-expanded", "false");
            searchInput.removeAttribute("aria-activedescendant");
        }
    };

    let suggestionTimer;
    let activeSuggestion = -1;
    const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
    }[char]));

    searchInput.addEventListener("input", () => {
        window.clearTimeout(suggestionTimer);
        const query = searchInput.value.trim();
        if (!suggestionsPanel || query.length < 2) {
            clearSuggestions();
            return;
        }

        suggestionTimer = window.setTimeout(async () => {
            const url = `${searchInput.dataset.suggestionsUrl}?q=${encodeURIComponent(query)}`;
            try {
                const response = await fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } });
                const data = await response.json();
                const results = data.results || [];
                if (!results.length) {
                    clearSuggestions();
                    return;
                }

                suggestionsPanel.innerHTML = results
                    .map((item, index) => `
                        <a class="search-suggestion-item" id="searchSuggestion${index}" role="option" aria-selected="false" href="${item.url}">
                            <span>${escapeHtml(item.name)}</span>
                            <small>${escapeHtml(item.meta || "")}</small>
                        </a>
                    `)
                    .join("");
                suggestionsPanel.classList.add("is-visible");
                searchInput.setAttribute("aria-expanded", "true");
                activeSuggestion = -1;
            } catch (error) {
                clearSuggestions();
            }
        }, 180);
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest(".search-form")) {
            clearSuggestions();
        }
    });

    searchInput.addEventListener("keydown", (event) => {
        if (!suggestionsPanel || !suggestionsPanel.classList.contains("is-visible")) {
            return;
        }
        const options = Array.from(suggestionsPanel.querySelectorAll('[role="option"]'));
        if (!options.length) {
            return;
        }
        if (event.key === "Escape") {
            clearSuggestions();
            return;
        }
        if (event.key === "Enter" && activeSuggestion >= 0) {
            event.preventDefault();
            options[activeSuggestion].click();
            return;
        }
        if (!['ArrowDown', 'ArrowUp'].includes(event.key)) {
            return;
        }
        event.preventDefault();
        activeSuggestion = event.key === "ArrowDown"
            ? (activeSuggestion + 1) % options.length
            : (activeSuggestion - 1 + options.length) % options.length;
        options.forEach((option, index) => option.setAttribute("aria-selected", String(index === activeSuggestion)));
        searchInput.setAttribute("aria-activedescendant", options[activeSuggestion].id);
        options[activeSuggestion].scrollIntoView({ block: "nearest" });
    });

    searchInput.addEventListener("focus", () => {
        searchInput.placeholder = "Try BP Monitor, Thermometer, Diabetes";
    });

    searchInput.addEventListener("blur", () => {
        searchInput.placeholder = "Search medicines, equipment, brands";
    });
});
