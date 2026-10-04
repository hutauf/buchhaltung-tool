from __future__ import annotations

import argparse

from _agent_common import fail, print_json
from autobookkeeping.checklist import ChecklistStore
from autobookkeeping.config import load_settings
from autobookkeeping.ebay_client import EbayTradingClient
from autobookkeeping.invoiz_client import InvoizClient
from autobookkeeping.invoiz_matching import find_invoice_matches
from autobookkeeping.local_invoices import prevent_invoiz_invoice_write
from autobookkeeping.vine_backend import VineBackendClient
from autobookkeeping.workflow import allocate_equal_prices, build_invoice_draft


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an invoiz invoice draft for an eBay order")
    parser.add_argument("order_id")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the invoice payload; draft creation is the safe default.",
    )
    parser.add_argument(
        "--lot-asins",
        nargs="+",
        help=(
            "Use the supplied Vine ASINs as separate invoice positions and split "
            "the eBay item total evenly to cents."
        ),
    )
    parser.add_argument(
        "--replace-draft-id",
        type=int,
        help="Replace this exact existing draft after verifying its order identity.",
    )
    parser.add_argument(
        "--customer-id",
        type=int,
        help="Reuse this existing invoiz customer instead of creating a customer record.",
    )
    parser.add_argument("--approved", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if not args.dry_run:
        prevent_invoiz_invoice_write()

    settings = load_settings()
    order = EbayTradingClient(settings).get_order(args.order_id)
    client = None
    replacement_customer_id = None
    if args.replace_draft_id is not None:
        client = InvoizClient(settings)
        replacement_customer_id = _verify_replace_target(
            client,
            args.replace_draft_id,
            args.order_id,
        )
        if args.customer_id is not None and args.customer_id != replacement_customer_id:
            fail(
                "--customer-id does not match the customer on the replacement draft: "
                f"{args.customer_id} != {replacement_customer_id}"
            )

    lot_items = _build_lot_items(order, settings, args.lot_asins)
    payload = build_invoice_draft(
        order,
        settings,
        lot_items=lot_items,
        customer_id=args.customer_id or replacement_customer_id,
    ).payload
    if args.dry_run:
        result = {"ok": True, "dry_run": True, "payload": payload}
        if lot_items is not None:
            result["lot_items"] = lot_items
        print_json(result)
        return 0

    checklist = ChecklistStore()
    checklist_item = checklist.find(
        args.order_id,
        order.sales_record_number,
    )
    existing_checklist_fields = {
        key: checklist_item.get(key)
        for key in ("invoice_id", "invoice_number", "invoice_locked_at")
        if checklist_item and checklist_item.get(key)
    }
    if existing_checklist_fields and not _is_requested_replacement(
        checklist_item,
        args.replace_draft_id,
    ):
        fail(
            f"Checklist already contains invoice data for order {args.order_id}: "
            f"{existing_checklist_fields}"
        )

    client = client or InvoizClient(settings)
    replaced_invoice_id = None
    existing = find_invoice_matches(client, order)
    if args.replace_draft_id is not None:
        unexpected = [
            match for match in existing if match.get("id") != args.replace_draft_id
        ]
        if unexpected:
            fail(f"Another invoiz invoice match exists for order {args.order_id}: {unexpected}")
        client.delete_invoice(args.replace_draft_id)
        _verify_invoice_deleted(client, args.replace_draft_id)
        remaining = find_invoice_matches(client, order)
        if remaining:
            fail(f"Invoice replacement did not remove old matches: {remaining}")
        checklist.clear_invoice(
            args.order_id,
            expected_invoice_id=args.replace_draft_id,
            sales_record_number=order.sales_record_number,
        )
        replaced_invoice_id = args.replace_draft_id
        existing = []
    if existing:
        fail(f"Existing invoiz invoice match for order {args.order_id}: {existing}")

    created = client.create_invoice(payload)
    invoice_id = created.get("data", {}).get("id") if isinstance(created, dict) else None
    if not invoice_id:
        fail(f"Could not determine created invoice id: {created}")
    detail = client.get_invoice(invoice_id)
    invoice = detail.get("data", {}).get("invoice", {}) if isinstance(detail, dict) else {}
    checklist.upsert(
        order.order_id,
        {
            "invoice_id": int(invoice_id),
            "invoice_number": None,
            "invoice_locked_at": None,
            "status": "rechnung_angelegt",
            "invoice_total": invoice.get("totalGross"),
            "sales_record_number": order.sales_record_number,
            "order_id_aliases": order.order_id_aliases,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "order_status": order.order_status,
        },
    )
    result = {"ok": True, "created_invoice": created, "invoice_after_create": detail}
    if lot_items is not None:
        result["lot_items"] = lot_items
    if replaced_invoice_id is not None:
        result["replaced_invoice_id"] = replaced_invoice_id
    print_json(result)
    return 0


def _build_lot_items(order, settings, asins: list[str] | None) -> list[dict] | None:
    if asins is None:
        return None
    if not asins:
        fail("--lot-asins requires at least one ASIN")
    if len(set(asins)) != len(asins):
        fail("--lot-asins contains duplicate ASINs")

    records = VineBackendClient(settings).get_asins(asins)
    by_asin = {record.asin: record for record in records}
    missing = [asin for asin in asins if asin not in by_asin]
    if missing:
        fail(f"ASIN not found in Vine backend: {', '.join(missing)}")

    prices = allocate_equal_prices(order.item_total, len(asins))
    lot_items = []
    for asin, price in zip(asins, prices):
        record = by_asin[asin]
        title = str(record.value.get("name") or "").strip()
        if not title:
            fail(f"Vine record has no product title: {asin}")
        lot_items.append(
            {
                "asin": asin,
                "title": title,
                "price": price,
                "usage_status": list(record.value.get("usageStatus", [])),
            }
        )
    return lot_items


def _is_requested_replacement(checklist_item: dict, replace_draft_id: int | None) -> bool:
    return (
        replace_draft_id is not None
        and checklist_item.get("invoice_id") == replace_draft_id
    )


def _verify_replace_target(client: InvoizClient, invoice_id: int, order_id: str) -> int:
    detail = client.get_invoice(invoice_id)
    invoice = detail.get("data", {}).get("invoice", {}) if isinstance(detail, dict) else {}
    customer_data = invoice.get("customerData") or {}
    identity = customer_data.get("number") or invoice.get("title", "").replace(
        "eBay Bestellung ", ""
    )
    if invoice.get("state") != "draft":
        fail(f"Replacement target is not a draft: {invoice_id}")
    if identity != order_id:
        fail(f"Replacement target belongs to another order: {invoice_id}")
    customer_id = invoice.get("customerId")
    if not customer_id:
        fail(f"Replacement target has no reusable customer id: {invoice_id}")
    return int(customer_id)


def _verify_invoice_deleted(client: InvoizClient, invoice_id: int) -> None:
    try:
        detail = client.get_invoice(invoice_id)
    except RuntimeError as error:
        message = str(error)
        if (
            "failed: 404" in message
            or "failed: 400" in message and "NOT_FOUND" in message
        ):
            return
        raise
    fail(f"Invoice still exists after deletion: {invoice_id} ({detail})")


if __name__ == "__main__":
    raise SystemExit(main())
