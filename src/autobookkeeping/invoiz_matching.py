from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Callable

from autobookkeeping.models import EbayOrder


ListFunction = Callable[..., Any]


def find_invoice_matches(client: Any, order: EbayOrder, limit: int = 100) -> list[dict]:
    """Find invoices even when invoiz's searchText endpoint misses exact values."""
    terms = _order_identifier_terms(order)
    direct = _search_endpoint_matches(
        client.list_invoices,
        terms,
        _invoice_result,
        lambda item, term: _term_matches(term, _invoice_haystack(item)),
    )
    recent = _list_items(client.list_invoices, limit=limit)
    fallback = match_invoice_items(recent, order)
    return _deduplicate([*direct, *fallback])


def find_expense_matches(
    client: Any,
    order: EbayOrder,
    invoice_numbers: list[str] | None = None,
    limit: int = 100,
) -> list[dict]:
    """Find expenses by order, tracking, or a verified final invoice number."""
    terms = _order_identifier_terms(
        order,
        *(invoice_numbers or []),
    )
    direct = _search_endpoint_matches(
        client.list_expenses,
        terms,
        _expense_result,
        lambda item, term: _term_matches(
            term,
            _text_haystack(item.get("description"), item.get("payee")),
        ),
    )
    recent = _list_items(client.list_expenses, limit=limit)
    fallback = match_expense_items(recent, terms)
    return _deduplicate([*direct, *fallback])


def match_invoice_items(invoices: list[dict], order: EbayOrder) -> list[dict]:
    terms = _order_identifier_terms(order)
    matches = []
    for invoice in invoices:
        haystack = _invoice_haystack(invoice)
        matched_terms = [term for term in terms if _term_matches(term, haystack)]
        if matched_terms:
            matches.append(_invoice_result(invoice, f"field:{matched_terms[0]}"))
            continue
        if _matches_order_identity(invoice, order):
            matches.append(_invoice_result(invoice, "customer+amount+date"))
    return _deduplicate(matches)


def match_expense_items(expenses: list[dict], terms: list[str]) -> list[dict]:
    matches = []
    for expense in expenses:
        haystack = _text_haystack(expense.get("description"), expense.get("payee"))
        matched_terms = [term for term in terms if _term_matches(term, haystack)]
        if matched_terms:
            matches.append(_expense_result(expense, f"field:{matched_terms[0]}"))
    return _deduplicate(matches)


def _search_endpoint_matches(
    list_fn: ListFunction,
    terms: list[str],
    result_fn: Callable[[dict, str], dict],
    matches_fn: Callable[[dict, str], bool],
) -> list[dict]:
    results = []
    for term in terms:
        for item in _list_items(list_fn, limit=10, search_text=term):
            if not matches_fn(item, term):
                continue
            results.append(result_fn(item, f"search:{term}"))
    return _deduplicate(results)


def _list_items(list_fn: ListFunction, limit: int, search_text: str = "") -> list[dict]:
    page_size = 20
    items = []
    offset = 0
    while offset < limit:
        requested = min(page_size, limit - offset)
        raw = list_fn(limit=requested, offset=offset, search_text=search_text)
        page = raw.get("data", []) if isinstance(raw, dict) else []
        items.extend(page)
        if len(page) < requested:
            break
        offset += len(page)
    return items[:limit]


def _matches_order_identity(invoice: dict, order: EbayOrder) -> bool:
    invoice_date = _date_part(invoice.get("date"))
    order_date = order.created_at.date() if order.created_at else None
    customer = invoice.get("customerData") or {}
    order_customer_name = _normalized(order.shipping_address.name)
    return all(
        (
            order_date is not None and invoice_date == order_date,
            bool(order_customer_name),
            _normalized(customer.get("name")) == order_customer_name,
            _amount(invoice.get("totalGross")) == _amount(order.total_value),
        )
    )


def _invoice_haystack(invoice: dict) -> str:
    customer = invoice.get("customerData") or {}
    parts = [
        invoice.get("title"),
        invoice.get("number"),
        customer.get("number"),
        customer.get("name"),
    ]
    for position in invoice.get("positions") or []:
        parts.extend((position.get("title"), position.get("description")))
    return _text_haystack(*parts)


def _invoice_result(invoice: dict, matched_by: str) -> dict:
    customer = invoice.get("customerData") or {}
    return {
        "matchedBy": matched_by,
        "id": invoice.get("id"),
        "number": invoice.get("number"),
        "date": invoice.get("date"),
        "title": invoice.get("title"),
        "state": invoice.get("state"),
        "lockedAt": invoice.get("lockedAt"),
        "totalGross": invoice.get("totalGross"),
        "customerNumber": customer.get("number"),
        "customerName": customer.get("name"),
    }


def _expense_result(expense: dict, matched_by: str) -> dict:
    return {
        "matchedBy": matched_by,
        "id": expense.get("id"),
        "date": expense.get("date"),
        "priceTotal": expense.get("priceTotal"),
        "description": expense.get("description"),
        "payee": expense.get("payee"),
        "receipts": expense.get("receipts", []),
    }


def _identifier_terms(*values: str | None) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _order_identifier_terms(order: EbayOrder, *extra: str | None) -> list[str]:
    return _identifier_terms(
        order.order_id,
        *order.order_id_aliases,
        order.sales_record_number,
        order.tracking_number,
        *extra,
    )


def _deduplicate(items: list[dict]) -> list[dict]:
    results = []
    seen = set()
    for item in items:
        key = ("id", item["id"]) if item.get("id") else ("item", repr(sorted(item.items())))
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def _text_haystack(*parts: Any) -> str:
    return "\n".join(str(part) for part in parts if part)


def _term_matches(term: str, haystack: str) -> bool:
    """Match a full identifier, not a short SRN embedded in another number."""
    if not term or not haystack:
        return False
    pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
    return re.search(pattern, haystack, flags=re.IGNORECASE) is not None


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _amount(value: Any) -> float | None:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _date_part(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None
