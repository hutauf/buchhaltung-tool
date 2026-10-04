from __future__ import annotations

import argparse

from _agent_common import print_json
from autobookkeeping.config import load_settings
from autobookkeeping.invoiz_client import InvoizClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Return recent invoiz invoices as JSON")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--search-text", default="")
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()

    client = InvoizClient(load_settings())
    raw = client.list_invoices(limit=args.limit, offset=args.offset, search_text=args.search_text)
    invoices = raw.get("data", []) if isinstance(raw, dict) else []
    if args.details:
        detailed = []
        for invoice in invoices:
            invoice_id = invoice.get("id")
            detail = client.get_invoice(invoice_id) if invoice_id else None
            inv = detail.get("data", {}).get("invoice", {}) if isinstance(detail, dict) else {}
            detailed.append(
                {
                    "id": inv.get("id"),
                    "number": inv.get("number"),
                    "state": inv.get("state"),
                    "lockedAt": inv.get("lockedAt"),
                    "date": inv.get("date"),
                    "customerData": inv.get("customerData"),
                    "totalGross": inv.get("totalGross"),
                    "positions": inv.get("positions", []),
                }
            )
        invoices = detailed
    print_json({"ok": True, "count": len(invoices), "invoices": invoices})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
