from __future__ import annotations

import argparse

from _agent_common import print_json
from autobookkeeping.checklist import ChecklistStore
from autobookkeeping.config import load_settings
from autobookkeeping.invoiz_client import InvoizClient
from autobookkeeping.local_invoices import prevent_invoiz_invoice_write


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize an invoiz invoice and return final number")
    parser.add_argument("invoice_id")
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args()

    if not args.approved:
        print_json({"ok": True, "dry_run": True, "invoice_id": args.invoice_id, "action": "lock"})
        return 0

    prevent_invoiz_invoice_write()
    client = InvoizClient(load_settings())
    result = client.lock_invoice(args.invoice_id)
    detail = client.get_invoice(args.invoice_id)
    invoice = detail.get("data", {}).get("invoice", {}) if isinstance(detail, dict) else {}
    order_id = invoice.get("customerData", {}).get("number") or invoice.get("title", "").replace("eBay Bestellung ", "")
    if order_id:
        ChecklistStore().upsert(
            str(order_id),
            {
                "invoice_id": int(args.invoice_id),
                "invoice_number": invoice.get("number"),
                "invoice_locked_at": invoice.get("lockedAt"),
                "status": "rechnung_abgeschlossen",
            },
        )
    print_json(
        {
            "ok": True,
            "lock_result": result,
            "invoice": {
                "id": invoice.get("id"),
                "number": invoice.get("number"),
                "state": invoice.get("state"),
                "lockedAt": invoice.get("lockedAt"),
                "totalGross": invoice.get("totalGross"),
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
