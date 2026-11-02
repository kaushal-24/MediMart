from decimal import Decimal, ROUND_HALF_UP

from core.checkout import get_checkout_config


MONEY_QUANTUM = Decimal("0.01")


def money(value):
    return Decimal(str(value or 0)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def calculate_order_charges(items, coupon=None, subtotal=None, customer_state=""):
    """Calculate the complete customer-visible charge breakdown for a cart/order."""
    items = list(items)
    checkout_config = get_checkout_config()
    subtotal = money(subtotal if subtotal is not None else sum(item.total_price for item in items))
    discount = money(coupon.calculate_discount(subtotal) if coupon else 0)
    taxable_subtotal = max(subtotal - discount, Decimal("0.00"))
    tax_amount = (
        money(taxable_subtotal * checkout_config.tax_rate_percent / Decimal("100"))
        if checkout_config.gst_enabled
        else Decimal("0.00")
    )
    same_state = bool(
        checkout_config.business_state
        and customer_state
        and checkout_config.business_state.strip().casefold() == str(customer_state).strip().casefold()
    )
    cgst_amount = money(tax_amount / Decimal("2")) if same_state else Decimal("0.00")
    sgst_amount = money(tax_amount - cgst_amount) if same_state else Decimal("0.00")
    igst_amount = tax_amount if tax_amount and not same_state else Decimal("0.00")
    commission_amount = money(subtotal * checkout_config.commission_rate_percent / Decimal("100"))
    handling_charge = money(checkout_config.handling_fee) if subtotal else Decimal("0.00")
    platform_fee = money(checkout_config.platform_fee) if subtotal else Decimal("0.00")
    delivery_charge = (
        Decimal("0.00")
        if subtotal == 0 or checkout_config.free_delivery
        else money(checkout_config.delivery_fee)
    )
    cold_chain_required = any(
        getattr(getattr(item.vendor_product, "product", None), "cold_chain_required", False)
        for item in items
    )
    cold_chain_charge = (
        money(checkout_config.cold_chain_fee)
        if cold_chain_required
        else Decimal("0.00")
    )
    total_amount = money(
        taxable_subtotal
        + tax_amount
        + handling_charge
        + platform_fee
        + delivery_charge
        + cold_chain_charge
    )
    return {
        "subtotal": subtotal,
        "discount": discount,
        "tax_amount": tax_amount,
        "tax_rate_percent": checkout_config.tax_rate_percent if checkout_config.gst_enabled else Decimal("0.00"),
        "gst_enabled": checkout_config.gst_enabled,
        "cgst_amount": cgst_amount,
        "sgst_amount": sgst_amount,
        "igst_amount": igst_amount,
        "commission_amount": commission_amount,
        "finance_test_mode": checkout_config.finance_test_mode,
        "handling_charge": handling_charge,
        "platform_fee": platform_fee,
        "delivery_charge": delivery_charge,
        "cold_chain_required": cold_chain_required,
        "cold_chain_charge": cold_chain_charge,
        "total_amount": total_amount,
    }
