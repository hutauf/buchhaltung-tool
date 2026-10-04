from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from autobookkeeping.config import Settings
from autobookkeeping.models import EbayOrder, ExpenseDraft, InvoiceDraft


def build_invoice_draft(
    order: EbayOrder,
    settings: Settings,
    lot_items: list[dict[str, Any]] | None = None,
    customer_id: int | None = None,
    source_label: str = "eBay",
    source_reference: str | None = None,
    include_zero_shipping: bool = False,
) -> InvoiceDraft:
    if settings.invoiz_pay_condition_id is None:
        raise RuntimeError("INVOIZ_PAY_CONDITION_ID fehlt. Bitte einmal /setting/payCondition prüfen.")

    articles: list[dict[str, Any]] = []
    vat_percent = settings.bookkeeping_vat_percent
    reference = source_reference or order.order_id
    source_text = f"{source_label} Bestellung {reference}"

    if lot_items is None:
        for item in order.items:
            article = {
                "title": item.title,
                "description": source_text,
                "unit": "Stk.",
                "amount": item.quantity,
                "vatPercent": vat_percent,
                "discount": 0,
            }
            _set_article_price(article, settings.bookkeeping_price_kind, item.price)
            articles.append(article)
    else:
        for lot_item in lot_items:
            article = {
                "title": lot_item["title"],
                "description": f"ASIN {lot_item['asin']} – eBay Bestellung {order.order_id}",
                "unit": "Stk.",
                "amount": 1,
                "vatPercent": vat_percent,
                "discount": 0,
            }
            _set_article_price(article, settings.bookkeeping_price_kind, lot_item["price"])
            articles.append(article)

    if order.shipping_cost or include_zero_shipping:
        shipping_article = {
            "title": settings.shipping_article_title,
            "description": order.shipping_service or "Versand",
            "unit": "Stk.",
            "amount": 1,
            "vatPercent": vat_percent,
            "discount": 0,
        }
        _set_article_price(shipping_article, settings.bookkeeping_price_kind, order.shipping_cost)
        articles.append(shipping_article)

    texts = {"introduction": settings.invoice_intro}
    if settings.invoice_conclusion:
        texts["conclusion"] = settings.invoice_conclusion

    payload: dict[str, Any] = {
        "date": _invoiz_day(order.shipped_at or order.paid_at or datetime.now(timezone.utc)),
        "title": source_text,
        "customerData": _customer_data(order),
        "payConditionId": settings.invoiz_pay_condition_id,
        "priceKind": settings.bookkeeping_price_kind,
        "texts": texts,
        "articles": articles,
        "infoSectionCustomFields": _custom_fields(
            order,
            source_label=source_label,
            source_reference=reference,
        ),
        "options": {"showArticleNumber": False},
    }
    if customer_id is not None:
        payload["customerId"] = customer_id
        payload.pop("customerData", None)
    if order.shipped_at:
        payload["deliveryDate"] = _invoiz_day(order.shipped_at)
    return InvoiceDraft(order_id=order.order_id, payload=payload)


def allocate_equal_prices(total: float, count: int) -> list[float]:
    """Split a gross item total into cent-exact, as-even-as-possible prices."""
    if count <= 0:
        raise ValueError("count must be greater than zero")

    total_cents = int(
        (Decimal(str(total)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    if total_cents < 0:
        raise ValueError("total must not be negative")

    base_cents, remainder = divmod(total_cents, count)
    return [
        (base_cents + (1 if index < remainder else 0)) / 100
        for index in range(count)
    ]


def build_dhl_expense_draft(
    order: EbayOrder,
    settings: Settings,
    receipt_id: int | None = None,
    receipt_path: Path | None = None,
    invoice_number: str | None = None,
    shipping_product: str | None = None,
    tracking_number: str | None = None,
    dhl_cart_id: str | None = None,
    source_label: str = "eBay",
    source_reference: str | None = None,
) -> ExpenseDraft:
    receipts = [{"id": receipt_id}] if receipt_id is not None else []
    payload = {
        "date": _invoiz_day(order.shipped_at or order.paid_at or datetime.now(timezone.utc)),
        "payee": settings.dhl_payee,
        "description": _expense_description(
            order,
            invoice_number=invoice_number,
            shipping_product=shipping_product,
            tracking_number=tracking_number,
            dhl_cart_id=dhl_cart_id,
            source_label=source_label,
            source_reference=source_reference,
        ),
        "payDate": _invoiz_day(order.shipped_at or order.paid_at or datetime.now(timezone.utc)),
        "priceTotal": order.shipping_cost,
        "vatPercent": 0,
        "payKind": settings.expense_pay_kind,
        "receipts": receipts,
    }
    return ExpenseDraft(order_id=order.order_id, payload=payload, receipt_path=receipt_path)


def summarize_order(order: EbayOrder) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "order_id_aliases": list(order.order_id_aliases),
        "sales_record_number": order.sales_record_number,
        "order_status": order.order_status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "buyer_username": order.buyer_username,
        "customer": order.shipping_address.name,
        "city": order.shipping_address.city,
        "total_value": order.total_value,
        "item_total": order.item_total,
        "shipping_cost": order.shipping_cost,
        "currency": order.currency,
        "tracking_number": order.tracking_number,
        "tracking_carrier": order.tracking_carrier,
        "items": [
            {
                "title": item.title,
                "quantity": item.quantity,
                "price": item.price,
                "currency": item.currency,
            }
            for item in order.items
        ],
    }


def _customer_data(order: EbayOrder) -> dict[str, Any]:
    address = order.shipping_address
    first_name, last_name = _split_name(address.name)
    customer_data = {
        "kind": "person",
        "number": order.order_id,
        "firstName": first_name,
        "lastName": last_name or address.name or order.buyer_username or "eBay Kunde",
        "countryIso": address.country_iso or "DE",
    }
    if address.street:
        customer_data["street"] = address.street
    if address.postal_code:
        customer_data["zipCode"] = address.postal_code
    if address.city:
        customer_data["city"] = address.city
    return customer_data


def _custom_fields(
    order: EbayOrder,
    source_label: str = "eBay",
    source_reference: str | None = None,
) -> list[dict[str, str]]:
    reference = source_reference or order.order_id
    fields = [{"label": f"{source_label} Bestellung", "value": reference}]
    if order.tracking_number:
        fields.append({"label": "Sendungsnummer", "value": order.tracking_number})
    if order.buyer_username:
        fields.append({"label": "eBay Käufer", "value": order.buyer_username})
    return fields[:3]


def _expense_description(
    order: EbayOrder,
    invoice_number: str | None = None,
    shipping_product: str | None = None,
    tracking_number: str | None = None,
    dhl_cart_id: str | None = None,
    source_label: str = "eBay",
    source_reference: str | None = None,
) -> str:
    reference = source_reference or order.order_id
    parts = [shipping_product or "DHL Versand", f"{source_label} Bestellung {reference}"]
    if invoice_number:
        parts.append(f"Rechnung {invoice_number}")
    effective_tracking_number = tracking_number or order.tracking_number
    if effective_tracking_number:
        parts.append(f"Sendungsnummer {effective_tracking_number}")
    if dhl_cart_id:
        parts.append(f"DHL Warenkorb {dhl_cart_id}")
    return " - ".join(parts)


def _set_article_price(article: dict[str, Any], price_kind: str, value: float) -> None:
    # invoiz returns priceGross on detail reads, but the create schema accepts price.
    article["price"] = value


def _split_name(name: str) -> tuple[str, str]:
    parts = name.strip().split()
    if len(parts) < 2:
        return "", name.strip()
    return " ".join(parts[:-1]), parts[-1]


def _invoiz_date(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _invoiz_day(value: datetime, timezone_name: str = "Europe/Berlin") -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local_date = value.astimezone(ZoneInfo(timezone_name)).date()
    return f"{local_date.isoformat()}T00:00:00.000Z"
