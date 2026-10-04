from __future__ import annotations

import argparse
from pathlib import Path

from _agent_common import fail, print_json
from autobookkeeping.checklist import ChecklistStore
from autobookkeeping.config import load_settings
from autobookkeeping.ebay_client import EbayTradingClient
from autobookkeeping.invoiz_client import InvoizClient
from autobookkeeping.workflow import build_dhl_expense_draft


def main() -> int:
    parser = argparse.ArgumentParser(description="Create DHL expense in invoiz for an eBay order")
    parser.add_argument("order_id")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--invoice-id")
    parser.add_argument("--invoice-number")
    parser.add_argument("--shipping-product", required=True)
    parser.add_argument(
        "--expense-amount",
        type=float,
        help="Actual DHL amount from the receipt when eBay shipping differs (for example free shipping)",
    )
    parser.add_argument("--tracking-number", help="DHL tracking number when eBay does not contain it")
    parser.add_argument("--dhl-cart-id")
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    order = EbayTradingClient(settings).get_order(args.order_id)
    client = InvoizClient(settings)
    invoice_number = args.invoice_number
    if args.invoice_id and not invoice_number:
        invoice = client.get_invoice(args.invoice_id)
        invoice_number = invoice.get("data", {}).get("invoice", {}).get("number")
    if not invoice_number:
        fail("invoice number is required; finalize invoice first or pass --invoice-number")

    preview = build_dhl_expense_draft(
        order,
        settings,
        invoice_number=invoice_number,
        shipping_product=args.shipping_product,
        tracking_number=args.tracking_number,
        dhl_cart_id=args.dhl_cart_id,
    ).payload
    if args.expense_amount is not None:
        preview["priceTotal"] = args.expense_amount
    if not args.approved:
        print_json({"ok": True, "dry_run": True, "payload": preview})
        return 0

    receipt_upload = client.upload_expense_receipt(args.receipt)
    receipt_id = receipt_upload.get("data", {}).get("id") if isinstance(receipt_upload, dict) else None
    if not receipt_id:
        fail(f"Could not determine receipt id: {receipt_upload}")
    payload = build_dhl_expense_draft(
        order,
        settings,
        receipt_id=int(receipt_id),
        receipt_path=args.receipt,
        invoice_number=invoice_number,
        shipping_product=args.shipping_product,
        tracking_number=args.tracking_number,
        dhl_cart_id=args.dhl_cart_id,
    ).payload
    if args.expense_amount is not None:
        payload["priceTotal"] = args.expense_amount
    created = client.create_expense(payload)
    expense_id = created.get("data", {}).get("id") if isinstance(created, dict) else None
    expense = client.get_expense(expense_id) if expense_id else None
    if args.receipt.exists():
        args.receipt.unlink()
    ChecklistStore().upsert(
        order.order_id,
        {
            "invoice_number": invoice_number,
            "invoice_id": int(args.invoice_id) if args.invoice_id else None,
            "expense_id": int(expense_id) if expense_id else None,
            "receipt_id": int(receipt_id),
            "status": "ausgabe_angelegt",
            "sales_record_number": order.sales_record_number,
            "order_id_aliases": order.order_id_aliases,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "order_status": order.order_status,
        },
    )
    print_json(
        {
            "ok": True,
            "receipt_upload": receipt_upload,
            "created_expense": created,
            "expense_after_create": expense,
            "local_receipt_deleted": not args.receipt.exists(),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
