from dataclasses import dataclass
from decimal import Decimal

from .models import CheckoutSettings


@dataclass(frozen=True)
class CheckoutConfig:
    delivery_fee: Decimal
    free_delivery: bool
    tax_rate_percent: Decimal
    handling_fee: Decimal
    platform_fee: Decimal
    cold_chain_fee: Decimal
    cod_max_order_value: Decimal
    cod_blocked_pincodes: frozenset
    finance_test_mode: bool = True
    gst_enabled: bool = True
    gstin: str = ""
    business_state: str = "Gujarat"
    invoice_prefix: str = "MM-INV"
    commission_rate_percent: Decimal = Decimal("0.00")
    settlement_days: int = 7


def _pincodes(value):
    return frozenset(
        part.strip()
        for part in str(value or "").replace("\n", ",").split(",")
        if part.strip()
    )


CHECKOUT_DEFAULTS = {
    "delivery_fee": Decimal("49.00"),
    "free_delivery": False,
    "tax_rate_percent": Decimal("18.00"),
    "handling_fee": Decimal("6.00"),
    "platform_fee": Decimal("24.00"),
    "cold_chain_fee": Decimal("1.00"),
    "cod_max_order_value": Decimal("1000.00"),
    "cod_blocked_pincodes": "",
    "finance_test_mode": True,
    "gst_enabled": True,
    "gstin": "",
    "business_state": "Gujarat",
    "invoice_prefix": "MM-INV",
    "commission_rate_percent": Decimal("0.00"),
    "settlement_days": 7,
}


def get_checkout_settings_record():
    """Return the single database-owned checkout settings record."""
    record, _ = CheckoutSettings.objects.get_or_create(
        pk=1,
        defaults=CHECKOUT_DEFAULTS,
    )
    return record


def get_checkout_config():
    """Return checkout pricing and COD rules stored in the database."""
    record = get_checkout_settings_record()
    return CheckoutConfig(
        delivery_fee=record.delivery_fee,
        free_delivery=record.free_delivery,
        tax_rate_percent=record.tax_rate_percent,
        handling_fee=record.handling_fee,
        platform_fee=record.platform_fee,
        cold_chain_fee=record.cold_chain_fee,
        cod_max_order_value=record.cod_max_order_value,
        cod_blocked_pincodes=_pincodes(record.cod_blocked_pincodes),
        finance_test_mode=record.finance_test_mode,
        gst_enabled=record.gst_enabled,
        gstin=record.gstin,
        business_state=record.business_state,
        invoice_prefix=record.invoice_prefix,
        commission_rate_percent=record.commission_rate_percent,
        settlement_days=record.settlement_days,
    )
