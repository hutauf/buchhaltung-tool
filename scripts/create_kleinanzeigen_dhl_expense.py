from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from _agent_common import fail, print_json
from autobookkeeping.checklist import ChecklistStore
from autobookkeeping.config import load_settings
from autobookkeeping.invoiz_client import InvoizClient
from autobookkeeping.invoiz_matching import find_expense_matches
from autobookkeeping.models import EbayOrder
from autobookkeeping.workflow import build_dhl_expense_draft


SOURCE_LABEL = "Kleinanzeigen"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a checked DHL expense for a Kleinanzeigen sale"
    )
    parser.add_argument("sale_id")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--invoice-id", type=int, required=True)
    parser.add_argument("--expense-amount", type=float, required=True)
    parser.add_argument("--sale-date", required=True, help="Sale date in DD.MM.YYYY format")
    parser.add_argument("--shipping-product", default="DHL Paket 2 kg")
    parser.add_argument("--tracking-number")
    parser.add_argument("--dhl-cart-id")
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()

    if not args.receipt.exists():
        fail(f"Receipt file does not exist: {args.receipt}")

    settings = load_settings()
    sale_datetime = _parse_date(args.sale_date)
    order = EbayOrder(
        order_id=args.sale_id,
        created_at=sale_datetime,
        paid_at=sale_datetime,
        shipped_at=sale_datetime,
        total_value=args.expense_amount,
        shipping_cost=args.expense_amount,
        shipping_service=args.shipping_product,
        tracking_number=args.tracking_number,
        tracking_carrier="DHL" if args.tracking_number else None,
    )
    client = InvoizClient(settings)
    invoice = _read_and_verify_invoice(client, args.invoice_id, args.sale_id)
    invoice_number = str(invoice.get("number") or "").strip()
    if not invoice_number:
        fail(f"Final invoice has no invoice number: {args.invoice_id}")

    existing = find_expense_matches(
        client,
        order,
        invoice_numbers=[invoice_number],
    )
    if existing:
        fail(f"Existing invoiz expense match for Kleinanzeigen sale {args.sale_id}: {existing}")

    preview = build_dhl_expense_draft(
        order,
        settings,
        invoice_number=invoice_number,
        shipping_product=args.shipping_product,
        tracking_number=args.tracking_number,
        dhl_cart_id=args.dhl_cart_id,
        source_label=SOURCE_LABEL,
        source_reference=args.sale_id,
    ).payload
    if not args.approved:
        print_json(
            {
                "ok": True,
                "dry_run": True,
                "sale_id": args.sale_id,
                "invoice_id": args.invoice_id,
                "invoice_number": invoice_number,
                "payload": preview,
            }
        )
        return 0

    receipt_upload = client.upload_expense_receipt(args.receipt)
    receipt_id = _receipt_id(receipt_upload)
    if receipt_id is None:
        fail(f"Could not determine uploaded receipt id: {receipt_upload}")

    payload = build_dhl_expense_draft(
        order,
        settings,
        receipt_id=receipt_id,
        receipt_path=args.receipt,
        invoice_number=invoice_number,
        shipping_product=args.shipping_product,
        tracking_number=args.tracking_number,
        dhl_cart_id=args.dhl_cart_id,
        source_label=SOURCE_LABEL,
        source_reference=args.sale_id,
    ).payload
    created = client.create_expense(payload)
    expense_id = _expense_id(created)
    if expense_id is None:
        fail(f"Could not determine created expense id: {created}")
    detail = client.get_expense(expense_id)
    expense = _expense_from_detail(detail)
    verification = _verify_expense(
        expense,
        expected_amount=args.expense_amount,
        expected_invoice_number=invoice_number,
        expected_sale_id=args.sale_id,
        expected_tracking=args.tracking_number,
        expected_cart_id=args.dhl_cart_id,
        expected_payee=settings.dhl_payee,
        expected_receipt_id=receipt_id,
    )
    if not verification["ok"]:
        fail(f"DHL expense verification failed: {verification['mismatches']}")

    args.receipt.unlink()
    checklist_item = ChecklistStore().upsert(
        args.sale_id,
        {
            "invoice_id": args.invoice_id,
            "invoice_number": invoice_number,
            "invoice_locked_at": invoice.get("lockedAt"),
            "expense_id": expense_id,
            "receipt_id": receipt_id,
            "status": "ok",
        },
    )
    print_json(
        {
            "ok": True,
            "sale_id": args.sale_id,
            "invoice_number": invoice_number,
            "receipt_upload": receipt_upload,
            "created_expense": created,
            "expense_after_create": detail,
            "verification": verification,
            "local_receipt_deleted": not args.receipt.exists(),
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


def _read_and_verify_invoice(client: InvoizClient, invoice_id: int, sale_id: str) -> dict:
    detail = client.get_invoice(invoice_id)
    invoice = detail.get("data", {}).get("invoice", {}) if isinstance(detail, dict) else {}
    customer_number = (invoice.get("customerData") or {}).get("number")
    if invoice.get("state") != "paid" or not invoice.get("lockedAt"):
        fail(f"Invoice is not finalized: {invoice_id}")
    if customer_number != sale_id:
        fail(f"Invoice belongs to another sale: {invoice_id}")
    return invoice


def _receipt_id(value) -> int | None:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        if value[0].get("id") is not None:
            return int(value[0]["id"])
    if isinstance(value, dict):
        if value.get("id") is not None:
            return int(value["id"])
        data = value.get("data")
        if isinstance(data, dict) and data.get("id") is not None:
            return int(data["id"])
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if data[0].get("id") is not None:
                return int(data[0]["id"])
    return None


def _expense_id(value) -> int | None:
    if not isinstance(value, dict):
        return None
    if value.get("id") is not None:
        return int(value["id"])
    data = value.get("data")
    if isinstance(data, dict) and data.get("id") is not None:
        return int(data["id"])
    return None


def _expense_from_detail(value) -> dict:
    if not isinstance(value, dict):
        return {}
    data = value.get("data")
    if isinstance(data, dict):
        nested = data.get("expense")
        if isinstance(nested, dict):
            return nested
        return data
    nested = value.get("expense")
    return nested if isinstance(nested, dict) else value


def _verify_expense(
    expense: dict,
    *,
    expected_amount: float,
    expected_invoice_number: str,
    expected_sale_id: str,
    expected_tracking: str | None,
    expected_cart_id: str | None,
    expected_payee: str,
    expected_receipt_id: int,
) -> dict:
    mismatches = {}
    if _amount(expense.get("priceTotal")) != _amount(expected_amount):
        mismatches["priceTotal"] = {
            "expected": round(expected_amount, 2),
            "actual": expense.get("priceTotal"),
        }
    if _amount(expense.get("vatPercent")) not in (None, 0):
        mismatches["vatPercent"] = {"expected": 0, "actual": expense.get("vatPercent")}
    if expense.get("payee") != expected_payee:
        mismatches["payee"] = {"expected": expected_payee, "actual": expense.get("payee")}

    description = str(expense.get("description") or "")
    required_parts = [
        f"{SOURCE_LABEL} Bestellung {expected_sale_id}",
        f"Rechnung {expected_invoice_number}",
    ]
    if expected_tracking:
        required_parts.append(f"Sendungsnummer {expected_tracking}")
    if expected_cart_id:
        required_parts.append(f"DHL Warenkorb {expected_cart_id}")
    missing_parts = [part for part in required_parts if part not in description]
    if missing_parts:
        mismatches["description"] = {
            "missing": missing_parts,
            "actual": description,
        }

    receipts = expense.get("receipts") or []
    receipt_ids = {
        int(receipt.get("id"))
        for receipt in receipts
        if isinstance(receipt, dict) and receipt.get("id") is not None
    }
    if expected_receipt_id not in receipt_ids:
        mismatches["receipts"] = {
            "expected_id": expected_receipt_id,
            "actual": receipts,
        }
    return {"ok": not mismatches, "mismatches": mismatches}


def _amount(value) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
