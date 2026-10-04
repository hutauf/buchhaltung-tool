from __future__ import annotations

import argparse
from zoneinfo import ZoneInfo

from _agent_common import fail, print_json
from autobookkeeping.checklist import ChecklistStore
from autobookkeeping.config import load_settings
from autobookkeeping.ebay_client import EbayTradingClient
from autobookkeeping.models import EbayOrder
from autobookkeeping.vine_backend import (
    VineBackendClient,
    candidate_matches,
    format_buyer_address,
    inventory_records,
    match_recommendation,
    sold_records,
    sold_usage_status,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Vine/Teilwert backend helper")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch")
    fetch_filter = fetch.add_mutually_exclusive_group()
    fetch_filter.add_argument("--sold-only", action="store_true")
    fetch_filter.add_argument("--inventory-only", action="store_true")
    fetch.add_argument("--limit", type=int, default=50)

    match = sub.add_parser("match")
    match.add_argument("--title", required=True)
    match.add_argument("--sale-price", type=float)
    match.add_argument("--limit", type=int, default=10)
    match.add_argument("--all-records", action="store_true")

    match_order = sub.add_parser("match-order")
    match_order.add_argument("order_id")
    match_order.add_argument("--limit", type=int, default=10)

    update = sub.add_parser("update-sale")
    update.add_argument("--asin", required=True)
    update.add_argument("--order-id")
    update.add_argument("--item-index", type=int)
    update.add_argument("--sale-price", type=float)
    update.add_argument("--sale-date")
    update.add_argument("--buyer-address")
    update.add_argument("--approved", action="store_true")

    args = parser.parse_args()
    settings = load_settings()
    client = VineBackendClient(settings)

    if args.command == "fetch":
        records = client.get_all()
        if args.sold_only:
            records = sold_records(records)
        elif args.inventory_only:
            records = inventory_records(records)
        print_json(
            {
                "ok": True,
                "count": len(records),
                "records": [_public_record(record) for record in records[: args.limit]],
            }
        )
        return 0

    if args.command == "match":
        records = client.get_all()
        if args.all_records:
            matches = candidate_matches(records, args.title, args.sale_price)[: args.limit]
            result = {"status": "ranked", "candidates": matches}
        else:
            result = match_recommendation(records, args.title, args.limit)
        print_json({"ok": True, **result})
        return 0

    if args.command == "match-order":
        order = EbayTradingClient(settings).get_order(args.order_id)
        records = client.get_all()
        sale_date = _sale_date(order)
        buyer_address = format_buyer_address(order.shipping_address, order.order_id)
        items = []
        for item_index, item in enumerate(order.items):
            recommendation = match_recommendation(records, item.title, args.limit)
            result = {
                "item_index": item_index,
                "title": item.title,
                "quantity": item.quantity,
                "sale_price_without_shipping": round(item.price * item.quantity, 2),
                "recommendation": recommendation,
            }
            if recommendation["status"] == "unique":
                candidate = recommendation["candidates"][0]
                result["proposed_update"] = {
                    "ASIN": candidate["ASIN"],
                    "productTitle": candidate["name"],
                    "usageStatus": sold_usage_status(candidate.get("usageStatus", [])),
                    "salePrice": round(item.price * item.quantity, 2),
                    "saleDate": sale_date,
                    "buyerAddress": buyer_address,
                }
            items.append(result)
        print_json(
            {
                "ok": True,
                "order_id": order.order_id,
                "sale_date": sale_date,
                "buyer_address": buyer_address,
                "items": items,
            }
        )
        return 0

    if args.command == "update-sale":
        records = client.get_all()
        record = next((item for item in records if item.asin == args.asin), None)
        if record is None:
            fail(f"ASIN not found: {args.asin}")

        order = None
        sale_price = args.sale_price
        sale_date = args.sale_date
        buyer_address = args.buyer_address
        if args.order_id:
            order = EbayTradingClient(settings).get_order(args.order_id)
            item = _selected_order_item(order, args.item_index)
            sale_price = (
                sale_price
                if sale_price is not None
                else round(item.price * item.quantity, 2)
            )
            sale_date = sale_date or _sale_date(order)
            buyer_address = buyer_address or format_buyer_address(
                order.shipping_address,
                order.order_id,
            )
        if sale_price is None:
            fail("--sale-price is required when --order-id is not supplied")
        if not sale_date:
            fail("--sale-date is required when --order-id is not supplied")

        value = dict(record.value)
        value.update(
            {
                "usageStatus": sold_usage_status(list(value.get("usageStatus", []))),
                "salePrice": sale_price,
                "saleDate": sale_date,
            }
        )
        if buyer_address is not None:
            value["buyerAddress"] = buyer_address

        proposed = {
            "ASIN": args.asin,
            "productTitle": value.get("name"),
            "usageStatus": value["usageStatus"],
            "salePrice": value["salePrice"],
            "saleDate": value["saleDate"],
            "buyerAddress": value.get("buyerAddress"),
        }
        if not args.approved:
            print_json({"ok": True, "dry_run": True, "proposed_update": proposed, "value": value})
            return 0

        # Persist the complete freshly-read record with a current timestamp.
        # Timestamp 0 only produces a transient merge that can be displaced by
        # the authoritative stored record on a later backend read.
        result = client.update_asin(args.asin, value)
        verified_records = client.get_asins([args.asin])
        if not verified_records:
            fail(f"ASIN missing after update: {args.asin}")
        verified = verified_records[0]
        verification = _verify_sale_update(verified.value, proposed)
        if not verification["ok"]:
            fail(f"Vine update verification failed: {verification['mismatches']}")

        checklist_item = None
        if order is not None:
            checklist_item = ChecklistStore().record_vine_sale(
                order.order_id,
                {
                    "asin": args.asin,
                    "product_title": verified.value.get("name"),
                    "sale_price": sale_price,
                    "sale_date": sale_date,
                    "verified": True,
                },
                sales_record_number=order.sales_record_number,
            )
        print_json(
            {
                "ok": True,
                "result": result,
                "ASIN": args.asin,
                "productTitle": verified.value.get("name"),
                "verified_record": _public_record(verified),
                "verification": verification,
                "checklist_item": checklist_item,
            }
        )
        return 0

    fail(f"Unknown command: {args.command}")
    return 1


def _selected_order_item(order: EbayOrder, item_index: int | None):
    if not order.items:
        fail(f"eBay order has no items: {order.order_id}")
    if item_index is None:
        if len(order.items) != 1:
            fail("--item-index is required for an eBay order with multiple items")
        return order.items[0]
    if item_index < 0 or item_index >= len(order.items):
        fail(f"Invalid --item-index {item_index}; order has {len(order.items)} items")
    return order.items[item_index]


def _sale_date(order: EbayOrder) -> str:
    source = order.paid_at or order.created_at
    if source is None:
        fail(f"eBay order has no sale date: {order.order_id}")
    if source.tzinfo is not None:
        source = source.astimezone(ZoneInfo("Europe/Berlin"))
    return source.strftime("%d.%m.%Y")


def _verify_sale_update(value: dict, expected: dict) -> dict:
    fields = ("usageStatus", "salePrice", "saleDate", "buyerAddress")
    mismatches = {
        field: {"expected": expected.get(field), "actual": value.get(field)}
        for field in fields
        if value.get(field) != expected.get(field)
    }
    return {"ok": not mismatches, "mismatches": mismatches}


def _public_record(record) -> dict:
    value = record.value
    return {
        "ASIN": record.asin,
        "last_update_time": record.last_update_time,
        "name": value.get("name"),
        "ordernumber": value.get("ordernumber"),
        "date": value.get("date"),
        "etv": value.get("etv"),
        "teilwert": value.get("teilwert"),
        "teilwert_v2": value.get("teilwert_v2"),
        "usageStatus": value.get("usageStatus", []),
        "salePrice": value.get("salePrice"),
        "saleDate": value.get("saleDate"),
        "buyerAddress": value.get("buyerAddress"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
