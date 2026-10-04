from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from autobookkeeping.config import load_settings
from autobookkeeping.dhl_receipts import download_receipt_from_link, likely_invoice_links
from autobookkeeping.ebay_client import EbayTradingClient
from autobookkeeping.imap_client import GmxImapClient
from autobookkeeping.invoiz_api_inspector import inspect_invoiz_api
from autobookkeeping.invoiz_client import InvoizClient
from autobookkeeping.workflow import (
    build_dhl_expense_draft,
    build_invoice_draft,
    summarize_order,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent-driven eBay/invoiz bookkeeping helpers")
    parser.add_argument("--env-file", type=Path, help="Optional .env override")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-connections")

    ebay_orders = sub.add_parser("ebay-orders")
    ebay_orders.add_argument("--days", type=int, default=30)
    ebay_orders.add_argument("--limit", type=int, default=20)
    ebay_orders.add_argument("--all", action="store_true", help="Include unshipped orders")

    preview = sub.add_parser("preview-order")
    preview.add_argument("order_id")

    create_invoice = sub.add_parser("create-invoice")
    create_invoice.add_argument("order_id")
    create_invoice.add_argument("--approved", action="store_true")

    get_invoice = sub.add_parser("get-invoice")
    get_invoice.add_argument("invoice_id")

    download_invoice = sub.add_parser("download-invoice")
    download_invoice.add_argument("invoice_id")
    download_invoice.add_argument("--output", type=Path)

    lock_invoice = sub.add_parser("lock-invoice")
    lock_invoice.add_argument("invoice_id")
    lock_invoice.add_argument("--approved", action="store_true")

    add_payment = sub.add_parser("add-invoice-payment")
    add_payment.add_argument("invoice_id")
    add_payment.add_argument("--amount", type=float, required=True)
    add_payment.add_argument("--notes", default="eBay Zahlung")
    add_payment.add_argument("--approved", action="store_true")

    dhl_mails = sub.add_parser("dhl-mails")
    dhl_mails.add_argument("--days", type=int, default=30)
    dhl_mails.add_argument("--limit", type=int, default=20)

    download_dhl = sub.add_parser("download-dhl-receipt")
    download_dhl.add_argument("url")
    download_dhl.add_argument("--output-dir", type=Path)

    create_expense = sub.add_parser("create-expense")
    create_expense.add_argument("order_id")
    create_expense.add_argument("--receipt", type=Path)
    create_expense.add_argument("--receipt-id", type=int)
    create_expense.add_argument("--invoice-id")
    create_expense.add_argument("--invoice-number")
    create_expense.add_argument("--shipping-product")
    create_expense.add_argument("--dhl-cart-id")
    create_expense.add_argument("--approved", action="store_true")

    get_expense = sub.add_parser("get-expense")
    get_expense.add_argument("expense_id")

    delete_receipt = sub.add_parser("delete-expense-receipt")
    delete_receipt.add_argument("receipt_id")
    delete_receipt.add_argument("--approved", action="store_true")

    pay_conditions = sub.add_parser("pay-conditions")
    pay_conditions.add_argument("--limit", type=int, default=100)

    inspect_api = sub.add_parser("inspect-invoiz-api")
    inspect_api.add_argument("path", type=Path, nargs="?", default=Path("invoiz_api.json"))

    args = parser.parse_args(argv)
    settings = load_settings(args.env_file)

    try:
        return _dispatch(args, settings)
    except Exception as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace, settings: Any) -> int:
    if args.command == "check-connections":
        result: dict[str, Any] = {}
        result["ebay"] = _check("ebay", lambda: len(EbayTradingClient(settings).get_orders(days=30, limit=1)))
        result["invoiz"] = _check("invoiz", lambda: InvoizClient(settings).connect())
        result["gmx_imap"] = _check("gmx_imap", lambda: len(GmxImapClient(settings).search_dhl_mails(days=7, limit=1)))
        _print_json(result)
        return 0

    if args.command == "ebay-orders":
        orders = EbayTradingClient(settings).get_orders(
            days=args.days,
            limit=args.limit,
            shipped_only=not args.all,
        )
        _print_json([summarize_order(order) for order in orders])
        return 0

    if args.command == "preview-order":
        order = EbayTradingClient(settings).get_order(args.order_id)
        invoice = build_invoice_draft(order, settings)
        expense = build_dhl_expense_draft(order, settings)
        _print_json(
            {
                "order": summarize_order(order),
                "invoice_payload": invoice.payload,
                "expense_payload_without_receipt": expense.payload,
            }
        )
        return 0

    if args.command == "create-invoice":
        order = EbayTradingClient(settings).get_order(args.order_id)
        draft = build_invoice_draft(order, settings)
        if not args.approved:
            _dry_run("invoice", draft.payload)
            return 0
        client = InvoizClient(settings)
        result = client.create_invoice(draft.payload)
        invoice_id = _extract_id(result)
        verify = client.get_invoice(invoice_id) if invoice_id is not None else None
        _print_json({"created_invoice": result, "invoice_after_create": verify})
        return 0

    if args.command == "get-invoice":
        _print_json(InvoizClient(settings).get_invoice(args.invoice_id))
        return 0

    if args.command == "download-invoice":
        content = InvoizClient(settings).download_invoice(args.invoice_id)
        from autobookkeeping.workspace import data_root
        output = args.output or data_root() / "downloads/invoices" / f"invoice-{args.invoice_id}.pdf"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        _print_json({"invoice_id": args.invoice_id, "output": str(output), "bytes": len(content)})
        return 0

    if args.command == "lock-invoice":
        if not args.approved:
            _dry_run("lock_invoice", {"invoice_id": args.invoice_id})
            return 0
        result = InvoizClient(settings).lock_invoice(args.invoice_id)
        verify = InvoizClient(settings).get_invoice(args.invoice_id)
        _print_json({"lock_result": result, "invoice_after_lock": verify})
        return 0

    if args.command == "add-invoice-payment":
        payload = {"amount": args.amount, "type": "payment", "notes": args.notes}
        if not args.approved:
            _dry_run("invoice_payment", {"invoice_id": args.invoice_id, **payload})
            return 0
        client = InvoizClient(settings)
        result = client.add_invoice_payment(args.invoice_id, payload)
        verify = client.get_invoice(args.invoice_id)
        _print_json({"payment_result": result, "invoice_after_payment": verify})
        return 0

    if args.command == "dhl-mails":
        candidates = GmxImapClient(settings).search_dhl_mails(days=args.days, limit=args.limit)
        _print_json(
            [
                {
                    "uid": candidate.uid,
                    "date": candidate.date,
                    "sender": candidate.sender,
                    "subject": candidate.subject,
                    "tracking_numbers": candidate.tracking_numbers,
                    "likely_invoice_links": likely_invoice_links(candidate.links),
                    "link_count": len(candidate.links),
                }
                for candidate in candidates
            ]
        )
        return 0

    if args.command == "download-dhl-receipt":
        from autobookkeeping.workspace import data_root
        path = download_receipt_from_link(args.url, args.output_dir or data_root() / "downloads/dhl")
        _print_json({"receipt_path": str(path)})
        return 0

    if args.command == "create-expense":
        order = EbayTradingClient(settings).get_order(args.order_id)
        client = InvoizClient(settings)
        invoice_number = args.invoice_number
        if args.invoice_id and not invoice_number:
            invoice_number = _invoice_number(client.get_invoice(args.invoice_id))
        receipt_id = args.receipt_id
        if args.receipt:
            if not args.approved:
                print("Dry run: receipt would be uploaded before expense creation.")
            elif receipt_id is None:
                receipt_result = client.upload_expense_receipt(args.receipt)
                receipt_id = _extract_receipt_id(receipt_result)
                print(json.dumps({"uploaded_receipt": receipt_result}, indent=2, ensure_ascii=False))
        draft = build_dhl_expense_draft(
            order,
            settings,
            receipt_id=receipt_id,
            receipt_path=args.receipt,
            invoice_number=invoice_number,
            shipping_product=args.shipping_product,
            dhl_cart_id=args.dhl_cart_id,
        )
        if not args.approved:
            _dry_run("expense", draft.payload)
            return 0
        result = client.create_expense(draft.payload)
        expense_id = _extract_id(result)
        verify = client.get_expense(expense_id) if expense_id is not None else None
        if args.receipt and args.receipt.exists():
            args.receipt.unlink()
        _print_json({"created_expense": result, "expense_after_create": verify})
        return 0

    if args.command == "get-expense":
        _print_json(InvoizClient(settings).get_expense(args.expense_id))
        return 0

    if args.command == "delete-expense-receipt":
        if not args.approved:
            _dry_run("delete_expense_receipt", {"receipt_id": args.receipt_id})
            return 0
        _print_json(InvoizClient(settings).delete_expense_receipt(args.receipt_id))
        return 0

    if args.command == "pay-conditions":
        _print_json(InvoizClient(settings).get_pay_conditions())
        return 0

    if args.command == "inspect-invoiz-api":
        _print_json(inspect_invoiz_api(args.path))
        return 0

    raise RuntimeError(f"Unknown command: {args.command}")


def _check(name: str, func: Any) -> dict[str, Any]:
    try:
        result = func()
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": f"{name}: {exc}"}


def _dry_run(kind: str, payload: dict[str, Any]) -> None:
    _print_json({"dry_run": True, "kind": kind, "payload": payload})


def _extract_receipt_id(value: Any) -> int:
    if isinstance(value, list) and value and isinstance(value[0], dict) and "id" in value[0]:
        return int(value[0]["id"])
    if isinstance(value, dict) and "id" in value:
        return int(value["id"])
    if isinstance(value, dict) and isinstance(value.get("data"), dict) and "id" in value["data"]:
        return int(value["data"]["id"])
    raise RuntimeError(f"Konnte receipt id aus invoiz-Antwort nicht erkennen: {value}")


def _extract_id(value: Any) -> int | None:
    if isinstance(value, dict):
        for key in ("id", "invoiceId", "expenseId"):
            if key in value:
                return int(value[key])
        for nested_key in ("invoice", "expense", "data"):
            nested = value.get(nested_key)
            if isinstance(nested, dict) and "id" in nested:
                return int(nested["id"])
    return None


def _invoice_number(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    invoice = value.get("data", {}).get("invoice", {})
    if isinstance(invoice, dict) and invoice.get("number"):
        return str(invoice["number"])
    if value.get("number"):
        return str(value["number"])
    return None


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    raise SystemExit(main())
