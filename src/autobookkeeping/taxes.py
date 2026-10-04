"""Explicit domestic gross-price tax policies; never infer a product's tax rate."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def decimal_money(value) -> Decimal:
    value = Decimal(str(value))
    if not value.is_finite():
        raise ValueError("Nicht endlicher Betrag")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate(positions: list[dict], small_business: bool, rates: list[int] | None = None) -> dict:
    if not positions:
        raise ValueError("Mindestens eine Position erforderlich")
    if small_business:
        if rates is not None and any(rate != 0 for rate in rates):
            raise ValueError("Kleinunternehmer dürfen hier keine Umsatzsteuer ausweisen")
        rates = [0] * len(positions)
    elif rates is None or len(rates) != len(positions) or any(rate not in (7, 19) for rate in rates):
        raise ValueError("Regelbesteuerung erfordert pro Position ausdrücklich 7 oder 19 Prozent")
    groups = {}
    for position, rate in zip(positions, rates, strict=True):
        gross = decimal_money(position["gross"])
        net = gross if small_business else decimal_money(gross / (1 + Decimal(rate) / 100))
        vat = gross - net
        position.update(net=str(net), vat=str(vat), vat_rate=rate)
        group = groups.setdefault(rate, {"net": Decimal(0), "vat": Decimal(0), "gross": Decimal(0)})
        for field, value in (("net", net), ("vat", vat), ("gross", gross)):
            group[field] += value
    totals = {field: str(sum((group[field] for group in groups.values()), Decimal(0)).quantize(Decimal("0.01")))
              for field in ("gross", "net", "vat")}
    return dict(totals, small_business=small_business,
                tax_treatment="small_business_exempt" if small_business else "domestic_vat",
                vat_rate=next(iter(groups)) if len(groups) == 1 else None,
                vat_rates=sorted(groups), vat_breakdown=[dict(vat_rate=rate, **{k: str(v) for k, v in group.items()})
                                                        for rate, group in sorted(groups.items())])
