from __future__ import annotations

import argparse

from _agent_common import print_json
from autobookkeeping.checklist import ChecklistStore
from autobookkeeping.config import load_settings
from autobookkeeping.ebay_client import EbayTradingClient
from autobookkeeping.invoiz_client import InvoizClient
from autobookkeeping.invoiz_matching import match_expense_items, match_invoice_items
from autobookkeeping.vine_backend import VineBackendClient, match_recommendation
from autobookkeeping.workflow import summarize_order


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile eBay orders with invoiz/checklist/Vine backend"
    )
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--invoiz-detail-limit", type=int, default=30)
    parser.add_argument("--write-checklist", action="store_true")
    parser.add_argument("--include-vine", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    ebay = EbayTradingClient(settings)
    invoiz = InvoizClient(settings)
    checklist = ChecklistStore()
    vine_records = VineBackendClient(settings).get_all() if args.include_vine else []
    recent_invoice_details = _recent_invoice_details(invoiz, limit=args.invoiz_detail_limit)
    recent_expenses = _recent_expenses(invoiz, limit=args.invoiz_detail_limit)

    orders = ebay.get_orders(days=args.days, limit=max(args.limit, 100), shipped_only=False)
    orders = [order for order in orders if order.paid_at is not None][: args.limit]

    results = []
    for order in orders:
        invoice_matches = match_invoice_items(recent_invoice_details, order)
        invoice_numbers = [match["number"] for match in invoice_matches if match.get("number")]
        expense_terms = [
            order.order_id,
            *order.order_id_aliases,
            order.sales_record_number or "",
            order.tracking_number or "",
            *invoice_numbers,
        ]
        expense_matches = match_expense_items(
            recent_expenses,
            [term for term in expense_terms if term],
        )
        detail = None
        if invoice_matches:
            invoice = invoice_matches[0]
            detail = {
                "id": invoice.get("id"),
                "number": invoice.get("number"),
                "state": invoice.get("state"),
                "lockedAt": invoice.get("lockedAt"),
                "totalGross": invoice.get("totalGross"),
            }
        vine_matches = []
        if vine_records:
            vine_matches = [
                {
                    "item_index": item_index,
                    "title": order_item.title,
                    "recommendation": match_recommendation(
                        vine_records,
                        order_item.title,
                        limit=5,
                    ),
                }
                for item_index, order_item in enumerate(order.items)
            ]

        item = {
            "order": summarize_order(order),
            "invoice_matches": invoice_matches,
            "invoice_detail": detail,
            "expense_matches": expense_matches,
            "vine_matches": vine_matches,
        }
        if args.write_checklist:
            updates = _checklist_updates(invoice_matches, detail, expense_matches)
            updates.update(
                {
                    "sales_record_number": order.sales_record_number,
                    "order_id_aliases": order.order_id_aliases,
                    "paid_at": order.paid_at.isoformat() if order.paid_at else None,
                    "order_status": order.order_status,
                }
            )
            item["checklist_item"] = checklist.upsert(order.order_id, updates)
        results.append(item)

    print_json({"ok": True, "count": len(results), "results": results})
    return 0


def _recent_invoice_details(invoiz: InvoizClient, limit: int) -> list[dict]:
    raw = invoiz.list_invoices(limit=limit, offset=0)
    invoices = raw.get("data", []) if isinstance(raw, dict) else []
    details = []
    for invoice in invoices:
        invoice_id = invoice.get("id")
        if not invoice_id:
            continue
        raw_detail = invoiz.get_invoice(invoice_id)
        detail = (
            raw_detail.get("data", {}).get("invoice", {})
            if isinstance(raw_detail, dict)
            else {}
        )
        if detail:
            details.append(detail)
    return details


def _recent_expenses(invoiz: InvoizClient, limit: int) -> list[dict]:
    raw = invoiz.list_expenses(limit=limit, offset=0)
    return raw.get("data", []) if isinstance(raw, dict) else []


def _checklist_updates(invoice_matches, invoice_detail, expense_matches) -> dict:
    updates = {}
    if invoice_matches:
        updates["invoice_id"] = invoice_matches[0].get("id")
    if invoice_detail:
        updates["invoice_number"] = invoice_detail.get("number")
        updates["invoice_locked_at"] = invoice_detail.get("lockedAt")
    if expense_matches:
        updates["expense_id"] = expense_matches[0].get("id")
    return updates


if __name__ == "__main__":
    raise SystemExit(main())
