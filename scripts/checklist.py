from __future__ import annotations

import argparse

from _agent_common import print_json, ROOT
from autobookkeeping.publication import Publication
from filelock import FileLock
import sys
from autobookkeeping.checklist import ChecklistStore


def run() -> int:
    parser = argparse.ArgumentParser(description="Read or update bookkeeping checklist")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")

    update = sub.add_parser("update")
    update.add_argument("order_id")
    update.add_argument("--status")
    update.add_argument("--invoice-id")
    update.add_argument("--invoice-number")
    update.add_argument("--invoice-locked-at")
    update.add_argument("--expense-id")
    update.add_argument("--receipt-id")
    update.add_argument("--vine-asin")
    update.add_argument("--sales-record-number")
    update.add_argument("--paid-at")
    update.add_argument("--order-status")
    update.add_argument("--note")

    clear_invoice = sub.add_parser("clear-invoice")
    clear_invoice.add_argument("order_id")
    clear_invoice.add_argument("--expected-invoice-id", type=int, required=True)

    vine_sale = sub.add_parser("vine-sale")
    vine_sale.add_argument("order_id")
    vine_sale.add_argument("--asin", required=True)
    vine_sale.add_argument("--product-title", required=True)
    vine_sale.add_argument("--sale-price", type=float, required=True)
    vine_sale.add_argument("--sale-date", required=True)

    args = parser.parse_args()
    store = ChecklistStore()
    if args.command == "list":
        print_json({"ok": True, "checklist": store.load()})
        return 0

    if args.command == "vine-sale":
        item = store.record_vine_sale(
            args.order_id,
            {
                "asin": args.asin,
                "product_title": args.product_title,
                "sale_price": args.sale_price,
                "sale_date": args.sale_date,
                "verified": True,
            },
        )
        print_json({"ok": True, "item": item})
        return 0

    if args.command == "clear-invoice":
        item = store.clear_invoice(
            args.order_id,
            expected_invoice_id=args.expected_invoice_id,
        )
        print_json({"ok": True, "item": item})
        return 0

    updates = {
        "status": args.status,
        "invoice_id": int(args.invoice_id) if args.invoice_id else None,
        "invoice_number": args.invoice_number,
        "invoice_locked_at": args.invoice_locked_at,
        "expense_id": int(args.expense_id) if args.expense_id else None,
        "receipt_id": int(args.receipt_id) if args.receipt_id else None,
        "vine_asin": args.vine_asin,
        "sales_record_number": args.sales_record_number,
        "paid_at": args.paid_at,
        "order_status": args.order_status,
        "note": args.note,
    }
    item = store.upsert(args.order_id, updates)
    print_json({"ok": True, "item": item})
    return 0


def main() -> int:
    command=sys.argv[1] if len(sys.argv)>1 else ''
    writes=command in ('update','clear-invoice','vine-sale')
    with Publication(ROOT,'checklist '+command,enabled=writes) as publication:
        if writes:
            with FileLock(ROOT/'output/archive.lock',timeout=0): result=run()
        else: result=run()
    if writes: print_json({'publication':publication.result})
    return result


if __name__ == "__main__":
    raise SystemExit(main())
