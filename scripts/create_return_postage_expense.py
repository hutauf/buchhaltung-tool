from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from _agent_common import fail, print_json
from autobookkeeping.checklist import ChecklistStore
from autobookkeeping.config import load_settings
from autobookkeeping.ebay_client import EbayTradingClient
from autobookkeeping.invoiz_client import InvoizClient


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a checked expense for a postage receipt used for an eBay return"
    )
    parser.add_argument("order_id")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--invoice-id", type=int, required=True)
    parser.add_argument("--expense-amount", type=float, required=True)
    parser.add_argument("--expense-date", required=True, help="Expense date in DD.MM.YYYY format")
    parser.add_argument("--document-number", required=True, help="Number on the supplier receipt")
    parser.add_argument("--payee", default="Deutsche Post AG")
    parser.add_argument("--shipping-product", default="Großbrief bis 500 g")
    parser.add_argument("--pay-kind", choices=("cash", "bank", "open"), default="bank")
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()

    if not args.receipt.exists():
        fail(f"Receipt file does not exist: {args.receipt}")

    expense_datetime = _parse_date(args.expense_date)
    settings = load_settings()
    order = EbayTradingClient(settings).get_order(args.order_id)
    client = InvoizClient(settings)

    invoice = _read_and_verify_invoice(client, args.invoice_id, args.order_id)
    invoice_number = str(invoice.get("number") or "").strip()
    if not invoice_number:
        fail(f"Invoice has no number: {args.invoice_id}")

    duplicate_candidates = _find_duplicate_candidates(
        client,
        order_id=args.order_id,
        invoice_number=invoice_number,
        document_number=args.document_number,
        amount=args.expense_amount,
        expense_date=expense_datetime,
    )
    if duplicate_candidates:
        fail(f"Existing invoiz expense match for return receipt {args.document_number}: {duplicate_candidates}")

    customer_name = order.shipping_address.name or "eBay-Kunde"
    description = _build_description(
        shipping_product=args.shipping_product,
        customer_name=customer_name,
        order_id=args.order_id,
        invoice=invoice,
        document_number=args.document_number,
    )
    preview = _build_payload(
        expense_datetime=expense_datetime,
        payee=args.payee,
        description=description,
        amount=args.expense_amount,
        pay_kind=args.pay_kind,
    )
    if not args.approved:
        print_json(
            {
                "ok": True,
                "dry_run": True,
                "order_id": args.order_id,
                "invoice_id": args.invoice_id,
                "invoice_number": invoice_number,
                "invoice_state": invoice.get("state"),
                "payload": preview,
            }
        )
        return 0

    receipt_upload = client.upload_expense_receipt(args.receipt)
    receipt_id = _receipt_id(receipt_upload)
    if receipt_id is None:
        fail(f"Could not determine receipt id: {receipt_upload}")

    payload = _build_payload(
        expense_datetime=expense_datetime,
        payee=args.payee,
        description=description,
        amount=args.expense_amount,
        pay_kind=args.pay_kind,
        receipt_id=receipt_id,
    )
    created = client.create_expense(payload)
    expense_id = _expense_id(created)
    if expense_id is None:
        fail(f"Could not determine created expense id: {created}")
    detail = client.get_expense(expense_id)
    expense = _expense_from_detail(detail)
    verification = _verify_expense(
        expense,
        expected_date=expense_datetime,
        expected_amount=args.expense_amount,
        expected_payee=args.payee,
        expected_pay_kind=args.pay_kind,
        expected_description_parts=(
            "Retour-Etikett",
            args.order_id,
            f"Rechnung {invoice_number}",
            args.document_number,
        ),
        expected_receipt_id=receipt_id,
    )
    if not verification["ok"]:
        fail(f"Return postage expense verification failed: {verification['mismatches']}")

    args.receipt.unlink()
    checklist_item = ChecklistStore().upsert(
        order.order_id,
        {
            "return_expense_id": expense_id,
            "return_receipt_id": receipt_id,
            "return_receipt_number": args.document_number,
            "return_expense_date": args.expense_date,
            "return_expense_amount": round(args.expense_amount, 2),
            "return_invoice_number": invoice_number,
            "return_expense_verified": True,
            "sales_record_number": order.sales_record_number,
            "order_id_aliases": order.order_id_aliases,
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "order_status": order.order_status,
        },
    )
    print_json(
        {
            "ok": True,
            "order_id": args.order_id,
            "invoice_id": args.invoice_id,
            "invoice_number": invoice_number,
            "invoice_state": invoice.get("state"),
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


def _invoiz_day(value: datetime) -> str:
    return f"{value.date().isoformat()}T00:00:00.000Z"


def _read_and_verify_invoice(client: InvoizClient, invoice_id: int, order_id: str) -> dict[str, Any]:
    detail = client.get_invoice(invoice_id)
    invoice = detail.get("data", {}).get("invoice", {}) if isinstance(detail, dict) else {}
    customer_number = (invoice.get("customerData") or {}).get("number")
    if customer_number != order_id:
        fail(f"Invoice belongs to another eBay order: {invoice_id}")
    if invoice.get("state") == "draft" and not invoice.get("lockedAt"):
        fail(f"Invoice is not finalized: {invoice_id}")
    return invoice


def _find_duplicate_candidates(
    client: InvoizClient,
    *,
    order_id: str,
    invoice_number: str,
    document_number: str,
    amount: float,
    expense_date: datetime,
) -> list[dict[str, Any]]:
    terms = [document_number, f"Rechnung {invoice_number}", "Retour-Etikett", order_id]
    items: dict[Any, dict[str, Any]] = {}
    for term in terms:
        raw = client.list_expenses(limit=100, offset=0, search_text=term)
        for item in _expense_items(raw):
            items[item.get("id") or repr(sorted(item.items()))] = item

    # The search endpoint can miss description fields, so inspect the current collection too.
    raw = client.list_expenses(limit=200, offset=0, search_text="")
    for item in _expense_items(raw):
        items[item.get("id") or repr(sorted(item.items()))] = item

    expected_date = _invoiz_day(expense_date)
    matches = []
    for item in items.values():
        description = str(item.get("description") or "")
        same_document = document_number in description
        same_return = (
            "Retour-Etikett" in description
            and order_id in description
            and _amount(item.get("priceTotal")) == _amount(amount)
            and str(item.get("date") or "").startswith(expected_date[:10])
        )
        if same_document or same_return:
            matches.append(
                {
                    "id": item.get("id"),
                    "date": item.get("date"),
                    "priceTotal": item.get("priceTotal"),
                    "description": item.get("description"),
                    "payee": item.get("payee"),
                }
            )
    return matches


def _build_description(
    *,
    shipping_product: str,
    customer_name: str,
    order_id: str,
    invoice: dict[str, Any],
    document_number: str,
) -> str:
    invoice_number = str(invoice.get("number") or "").strip()
    state = str(invoice.get("state") or "").strip().casefold()
    cancellation = (invoice.get("metaData") or {}).get("cancellation") or {}
    state_note = ""
    if state == "cancelled":
        cancellation_number = str(cancellation.get("number") or "").strip()
        state_note = " (Rechnung storniert"
        if cancellation_number:
            state_note += f"; Storno {cancellation_number}"
        state_note += ")"
    return (
        f"{shipping_product} - Retour-Etikett für retournierte Ware von {customer_name}"
        f" - eBay Bestellung {order_id} - Rechnung {invoice_number}{state_note}"
        f" - Deutsche-Post-Rechnung {document_number}"
    )


def _build_payload(
    *,
    expense_datetime: datetime,
    payee: str,
    description: str,
    amount: float,
    pay_kind: str,
    receipt_id: int | None = None,
) -> dict[str, Any]:
    return {
        "date": _invoiz_day(expense_datetime),
        "payee": payee,
        "description": description,
        "payDate": _invoiz_day(expense_datetime),
        "priceTotal": amount,
        "vatPercent": 0,
        "payKind": pay_kind,
        "receipts": [{"id": receipt_id}] if receipt_id is not None else [],
    }


def _expense_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    data = value.get("data")
    return data if isinstance(data, list) else []


def _receipt_id(value: Any) -> int | None:
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


def _expense_id(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    if value.get("id") is not None:
        return int(value["id"])
    data = value.get("data")
    if isinstance(data, dict) and data.get("id") is not None:
        return int(data["id"])
    return None


def _expense_from_detail(value: Any) -> dict[str, Any]:
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
    expense: dict[str, Any],
    *,
    expected_date: datetime,
    expected_amount: float,
    expected_payee: str,
    expected_pay_kind: str,
    expected_description_parts: tuple[str, ...],
    expected_receipt_id: int,
) -> dict[str, Any]:
    mismatches: dict[str, Any] = {}
    expected_day = _invoiz_day(expected_date)
    if not str(expense.get("date") or "").startswith(expected_day[:10]):
        mismatches["date"] = {"expected": expected_day, "actual": expense.get("date")}
    if _amount(expense.get("priceTotal")) != _amount(expected_amount):
        mismatches["priceTotal"] = {
            "expected": round(expected_amount, 2),
            "actual": expense.get("priceTotal"),
        }
    if _amount(expense.get("vatPercent")) not in (None, 0):
        mismatches["vatPercent"] = {"expected": 0, "actual": expense.get("vatPercent")}
    if expense.get("payee") != expected_payee:
        mismatches["payee"] = {"expected": expected_payee, "actual": expense.get("payee")}
    if expense.get("payKind") not in (None, expected_pay_kind):
        mismatches["payKind"] = {"expected": expected_pay_kind, "actual": expense.get("payKind")}

    description = str(expense.get("description") or "")
    missing_parts = [part for part in expected_description_parts if part not in description]
    if missing_parts:
        mismatches["description"] = {"missing": missing_parts, "actual": description}

    receipts = expense.get("receipts") or expense.get("expenseReceipts") or []
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


def _amount(value: Any) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
