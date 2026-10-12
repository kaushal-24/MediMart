document.addEventListener("DOMContentLoaded", () => {
    const root = document.querySelector("[data-payment-modal]");
    if (!root) return;

    const modalElement = root;
    const modal = window.bootstrap?.Modal.getOrCreateInstance(modalElement);
    const form = root.querySelector("[data-payment-contact-form]");
    const button = root.querySelector("#razorpayProceedButton");
    const status = root.querySelector("[data-payment-status]");
    const errorElement = root.querySelector("[data-payment-contact-error]");
    const emailInput = root.querySelector("#razorpayContactEmail");
    const phoneInput = root.querySelector("#razorpayContactPhone");
    const csrfToken = form?.querySelector("input[name='csrfmiddlewaretoken']")?.value || "";
    let activeGatewayOrderId = "";

    if (!form || !button) return;

    const setStatus = (message, isError = false) => {
        if (!status) return;
        status.textContent = message;
        status.classList.toggle("text-danger", isError);
        status.classList.toggle("text-success", !isError);
    };

    const setBusy = (busy) => {
        button.disabled = busy;
        button.setAttribute("aria-busy", String(busy));
        button.innerHTML = busy
            ? '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Preparing secure payment'
            : '<i class="bi bi-lock-fill me-2" aria-hidden="true"></i>Continue to secure payment';
    };

    const reportFailure = (failure) => fetch(root.dataset.failureUrl, {
        method: "POST",
        headers: {
            "X-CSRFToken": csrfToken,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({
            razorpay_order_id: failure?.metadata?.order_id || activeGatewayOrderId,
            razorpay_payment_id: failure?.metadata?.payment_id || "",
            error: failure || {},
        }),
    }).catch(() => {});

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        errorElement.textContent = "";
        if (!form.checkValidity()) {
            form.classList.add("was-validated");
            form.reportValidity();
            return;
        }

        setBusy(true);
        setStatus("Preparing secure payment...");
        try {
            const orderResponse = await fetch(root.dataset.createUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                credentials: "same-origin",
                body: new URLSearchParams(new FormData(form)),
            });
            const orderData = await orderResponse.json();
            if (!orderResponse.ok || !orderData.ok) {
                const fieldError = orderData.fields && Object.values(orderData.fields)[0];
                if (errorElement) errorElement.textContent = fieldError || orderData.error || "Unable to start payment.";
                throw new Error(orderData.error || "Unable to start payment.");
            }

            activeGatewayOrderId = orderData.order_id;
            const razorpay = new window.Razorpay({
                key: root.dataset.keyId,
                amount: orderData.amount,
                currency: orderData.currency,
                name: "MediMart",
                description: `Order ${root.dataset.orderLabel}`,
                order_id: orderData.order_id,
                prefill: {
                    name: root.dataset.customerName,
                    email: emailInput.value.trim(),
                    contact: phoneInput.value.trim(),
                },
                notes: { order_number: root.dataset.orderLabel },
                modal: {
                    ondismiss: () => {
                        setStatus("Payment cancelled. You can try again whenever you are ready.");
                        setBusy(false);
                        window.setTimeout(() => modal?.show(), 250);
                    },
                },
                handler: async (response) => {
                    try {
                        setStatus("Verifying payment...");
                        const verifyResponse = await fetch(root.dataset.verifyUrl, {
                            method: "POST",
                            headers: {
                                "X-CSRFToken": csrfToken,
                                "X-Requested-With": "XMLHttpRequest",
                                "Accept": "application/json",
                                "Content-Type": "application/x-www-form-urlencoded",
                            },
                            credentials: "same-origin",
                            body: new URLSearchParams({
                                razorpay_order_id: response.razorpay_order_id,
                                razorpay_payment_id: response.razorpay_payment_id,
                                razorpay_signature: response.razorpay_signature,
                            }),
                        });
                        const verifyData = await verifyResponse.json();
                        if (!verifyResponse.ok || !verifyData.ok) throw new Error(verifyData.error || "Payment verification failed.");
                        window.location.assign(verifyData.redirect_url);
                    } catch (error) {
                        setStatus(error.message || "Payment verification failed. Please contact support.", true);
                        setBusy(false);
                        window.setTimeout(() => modal?.show(), 250);
                    }
                },
            });

            razorpay.on("payment.failed", (response) => {
                const failure = response.error || {};
                setStatus(failure.description || "Payment failed. You were not charged.", true);
                reportFailure(failure);
                setBusy(false);
                window.setTimeout(() => modal?.show(), 250);
            });

            modal?.hide();
            window.setTimeout(() => razorpay.open(), 250);
        } catch (error) {
            setStatus(error.message || "Unable to start payment. Please try again.", true);
            setBusy(false);
        }
    });
});
