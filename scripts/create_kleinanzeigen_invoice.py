from __future__ import annotations

import argparse
from datetime import UTC, datetime

from _agent_common import fail, print_json
from autobookkeeping.checklist import ChecklistStore
from autobookkeeping.config import load_settings
from autobookkeeping.invoiz_client import InvoizClient
from autobookkeeping.invoiz_matching import find_invoice_matches
from autobookkeeping.models import Address, EbayOrder, EbayOrderItem
from autobookkeeping.vine_backend import VineBackendClient
from autobookkeeping.workflow import build_invoice_draft


SOURCE_LABEL = "Kleinanzeigen"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a checked Kleinanzeigen invoice draft in invoiz"
    )
    parser.add_argument("sale_id", help="Stable Kleinanzeigen/DHL reference, e.g. the cart ID")
    parser.add_argument("--asin", required=True)
    parser.add_argument("--item-price", type=float, required=True)
    parser.add_argument("--shipping-price", type=float, required=True)
    parser.add_argument("--sale-date", required=True, help="Sale date in DD.MM.YYYY format")
    parser.add_argument("--buyer-name", required=True)
    parser.add_argument("--street", default="")
    parser.add_argument("--postal-code", default="")
    parser.add_argument("--city", default="")
    parser.add_argument("--tracking-number")
    parser.add_argument("--shipping-description", default="DHL Paket 2 kg")
    parser.add_argument("--payment-note", default="Zahlung bereits erhalten.")
    parser.add_argument(
        "--pay-condition-name",
        default=SOURCE_LABEL,
        help="Existing invoiz payment condition name (default: Kleinanzeigen).",
    )
    parser.add_argument(
        "--allow-storniert",
        action="store_true",
        help="Allow a Vine record currently marked storniert; it can be updated to verkauft later.",
    )
    parser.add_argument("--replace-draft-id", type=int)
    parser.add_argument("--customer-id", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    sale_datetime = _parse_date(args.sale_date)
    order = EbayOrder(
        order_id=args.sale_id,
        created_at=sale_datetime,
        paid_at=sale_datetime,
        shipped_at=sale_datetime,
        total_value=round(args.item_price + args.shipping_price, 2),
        shipping_cost=args.shipping_price,
        shipping_service=args.shipping_description,
        tracking_number=args.tracking_number,
        tracking_carrier="DHL" if args.tracking_number else None,
        shipping_address=Address(
            name=args.buyer_name,
            street1=args.street,
            postal_code=args.postal_code,
            city=args.city,
            country="Deutschland",
            country_iso="DE",
        ),
        items=[EbayOrderItem(title="", price=args.item_price)],
    )

    vine_record = _read_vine_record(settings, args.asin)
    product_title = str(vine_record.value.get("name") or "").strip()
    if not product_title:
        fail(f"Vine record has no product title: {args.asin}")
    usage_status = vine_record.value.get("usageStatus", [])
    if "Lager" not in usage_status and not (
        args.allow_storniert and "storniert" in usage_status
    ):
        fail(f"Vine ASIN is not currently marked Lager: {args.asin}")
    order.items[0].title = product_title

    client = InvoizClient(settings)
    pay_condition_id = _pay_condition_id(client, args.pay_condition_name)
    settings.invoiz_pay_condition_id = pay_condition_id
    customer_id = args.customer_id
    checklist_item = next(
        (
            item
            for item in ChecklistStore().load().get("items", [])
            if item.get("order_id") == args.sale_id
        ),
        None,
    )
    existing_checklist_fields = {
        key: checklist_item.get(key)
        for key in ("invoice_id", "invoice_number", "expense_id")
        if checklist_item and checklist_item.get(key)
    }
    if existing_checklist_fields and args.replace_draft_id is None:
        fail(
            f"Checklist already contains bookkeeping data for {args.sale_id}: "
            f"{existing_checklist_fields}"
        )

    existing = find_invoice_matches(client, order)
    if args.replace_draft_id is not None:
        target = client.get_invoice(args.replace_draft_id)
        target_invoice = (
            target.get("data", {}).get("invoice", {})
            if isinstance(target, dict)
            else {}
        )
        if target_invoice.get("state") != "draft":
            fail(f"Replacement target is not a draft: {args.replace_draft_id}")
        if (target_invoice.get("customerData") or {}).get("number") != args.sale_id:
            fail(f"Replacement target belongs to another sale: {args.replace_draft_id}")
        target_customer_id = target_invoice.get("customerId")
        if target_customer_id is not None:
            if customer_id is not None and int(customer_id) != int(target_customer_id):
                fail(
                    "--customer-id does not match the customer on the replacement draft: "
                    f"{customer_id} != {target_customer_id}"
                )
            customer_id = int(target_customer_id)
        if customer_id is None:
            fail(f"Replacement target has no reusable customer id: {args.replace_draft_id}")
        unexpected = [
            match for match in existing if match.get("id") != args.replace_draft_id
        ]
        if unexpected:
            fail(f"Another invoiz invoice match exists for {args.sale_id}: {unexpected}")
        client.delete_invoice(args.replace_draft_id)
        _verify_invoice_deleted(client, args.replace_draft_id)
        if checklist_item and checklist_item.get("invoice_id") == args.replace_draft_id:
            ChecklistStore().clear_invoice(
                args.sale_id,
                expected_invoice_id=args.replace_draft_id,
            )
        existing = []
    elif existing:
        fail(f"Existing invoiz invoice match for Kleinanzeigen sale {args.sale_id}: {existing}")

    draft = build_invoice_draft(
        order,
        settings,
        customer_id=customer_id,
        source_label=SOURCE_LABEL,
        source_reference=args.sale_id,
        include_zero_shipping=True,
    )
    draft.payload["articles"][0]["description"] = (
        f"ASIN {args.asin} - {SOURCE_LABEL} Bestellung {args.sale_id}"
    )
    shipping_position = next(
        (
            article
            for article in draft.payload["articles"]
            if article.get("title") == "Versandkosten"
        ),
        None,
    )
    if shipping_position is not None:
        shipping_position["description"] = args.shipping_description
    if args.payment_note:
        draft.payload.setdefault("texts", {})["conclusion"] = args.payment_note
    if args.dry_run:
        print_json(
            {
                "ok": True,
                "dry_run": True,
                "source": SOURCE_LABEL,
                "sale_id": args.sale_id,
                "asin": args.asin,
                "product_title": product_title,
                "pay_condition_id": pay_condition_id,
                "invoice_payload": draft.payload,
            }
        )
        return 0

    created = client.create_invoice(draft.payload)
    invoice_id = _invoice_id(created)
    if invoice_id is None:
        fail(f"Could not determine created invoice id: {created}")
    detail = client.get_invoice(invoice_id)
    invoice = detail.get("data", {}).get("invoice", {}) if isinstance(detail, dict) else {}
    verification = _verify_invoice(
        invoice,
        sale_id=args.sale_id,
        sale_date=args.sale_date,
        buyer_name=args.buyer_name,
        street=args.street,
        postal_code=args.postal_code,
        city=args.city,
        asin=args.asin,
        product_title=product_title,
        item_price=args.item_price,
        shipping_price=args.shipping_price,
        total=args.item_price + args.shipping_price,
        pay_condition_id=pay_condition_id,
    )
    if not verification["ok"]:
        fail(f"Invoice draft verification failed: {verification['mismatches']}")

    checklist_item = ChecklistStore().upsert(
        args.sale_id,
        {
            "invoice_id": invoice_id,
            "invoice_total": invoice.get("totalGross"),
            "status": "rechnung_angelegt",
        },
    )
    print_json(
        {
            "ok": True,
            "source": SOURCE_LABEL,
            "sale_id": args.sale_id,
            "asin": args.asin,
            "product_title": product_title,
            "pay_condition_id": pay_condition_id,
            "created_invoice": created,
            "invoice_after_create": detail,
            "verification": verification,
            "checklist_item": checklist_item,
        }
    )
    return 0


def _parse_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%d.%m.%Y").replace(tzinfo=UTC)
    except ValueError:
        fail(f"Invalid date {value!r}; expected DD.MM.YYYY")
        raise AssertionError("unreachable")


def _read_vine_record(settings, asin: str):
    records = VineBackendClient(settings).get_asins([asin])
    record = next((record for record in records if record.asin == asin), None)
    if record is None:
        fail(f"ASIN not found in Vine backend: {asin}")
    return record


def _pay_condition_id(client: InvoizClient, name: str) -> int:
    response = client.get_pay_conditions()
    conditions = response.get("data", []) if isinstance(response, dict) else []
    for condition in conditions:
        if str(condition.get("name") or "").strip().casefold() == name.strip().casefold():
            return int(condition["id"])
    fail(f"No invoiz pay condition named {name!r} was found")
    raise AssertionError("unreachable")


def _invoice_id(created) -> int | None:
    if not isinstance(created, dict):
        return None
    data = created.get("data")
    if isinstance(data, dict) and data.get("id") is not None:
        return int(data["id"])
    if created.get("id") is not None:
        return int(created["id"])
    return None


def _verify_invoice(
    invoice: dict,
    *,
    sale_id: str,
    sale_date: str,
    buyer_name: str,
    street: str,
    postal_code: str,
    city: str,
    asin: str,
    product_title: str,
    item_price: float,
    shipping_price: float,
    total: float,
    pay_condition_id: int,
) -> dict:
    customer = invoice.get("customerData") or {}
    positions = invoice.get("positions") or []
    mismatches = {}
    expected_date = datetime.strptime(sale_date, "%d.%m.%Y").date().isoformat()
    actual_date = str(invoice.get("date") or "")[:10]
    required_customer_fields = {
        "number": sale_id,
        "name": buyer_name,
        "countryIso": "DE",
    }
    if street:
        required_customer_fields["street"] = street
    if postal_code:
        required_customer_fields["zipCode"] = postal_code
    if city:
        required_customer_fields["city"] = city
    if invoice.get("state") != "draft":
        mismatches["state"] = {"expected": "draft", "actual": invoice.get("state")}
    if invoice.get("payConditionId") != pay_condition_id:
        mismatches["payConditionId"] = {
            "expected": pay_condition_id,
            "actual": invoice.get("payConditionId"),
        }
    if actual_date != expected_date:
        mismatches["date"] = {"expected": expected_date, "actual": invoice.get("date")}
    for field, expected in required_customer_fields.items():
        if customer.get(field) != expected:
            mismatches[f"customerData.{field}"] = {
                "expected": expected,
                "actual": customer.get(field),
            }
    if _amount(invoice.get("totalGross")) != _amount(total):
        mismatches["totalGross"] = {
            "expected": round(total, 2),
            "actual": invoice.get("totalGross"),
        }

    product_match = next(
        (
            position
            for position in positions
            if asin in str(position.get("description") or "")
            and _amount(position.get("priceGross")) == _amount(item_price)
        ),
        None,
    )
    if product_match is None:
        product_match = next(
            (
                position
                for position in positions
                if _amount(position.get("priceGross")) == _amount(item_price)
                and str(position.get("title") or "").startswith(product_title[:20])
            ),
            None,
        )
    if product_match is None:
        mismatches["product_position"] = {
            "expected_price": round(item_price, 2),
            "expected_asin": asin,
            "actual": positions,
        }
    shipping_match = next(
        (
            position
            for position in positions
            if str(position.get("title") or "") == "Versandkosten"
            and _amount(position.get("priceGross")) == _amount(shipping_price)
        ),
        None,
    )
    if shipping_match is None:
        mismatches["shipping_position"] = {
            "expected_price": round(shipping_price, 2),
            "actual": positions,
        }
    return {"ok": not mismatches, "mismatches": mismatches}


def _amount(value) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _verify_invoice_deleted(client: InvoizClient, invoice_id: int) -> None:
    try:
        client.get_invoice(invoice_id)
    except RuntimeError as error:
        message = str(error)
        if "failed: 404" in message or ("failed: 400" in message and "NOT_FOUND" in message):
            return
        raise
    fail(f"Invoice still exists after replacement deletion: {invoice_id}")


if __name__ == "__main__":
    raise SystemExit(main())
