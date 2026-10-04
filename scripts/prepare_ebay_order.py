from __future__ import annotations

import argparse

from _agent_common import print_json
from autobookkeeping.config import load_settings
from autobookkeeping.ebay_client import EbayTradingClient
from autobookkeeping.invoiz_client import InvoizClient
from autobookkeeping.invoiz_matching import find_expense_matches, find_invoice_matches
from autobookkeeping.workflow import build_dhl_expense_draft, build_invoice_draft, summarize_order


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare invoice/expense drafts for one eBay order")
    parser.add_argument("order_id")
    parser.add_argument("--invoice-number", help="Final invoiz invoice number, when already known")
    parser.add_argument("--shipping-product", help="Example: DHL Paket S")
    parser.add_argument("--tracking-number", help="DHL tracking number when eBay does not contain it")
    parser.add_argument("--dhl-cart-id")
    parser.add_argument("--skip-invoiz-check", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    order = EbayTradingClient(settings).get_order(args.order_id)
    invoice_draft = build_invoice_draft(order, settings).payload
    expense_draft = build_dhl_expense_draft(
        order,
        settings,
        invoice_number=args.invoice_number or "<nach Rechnungserstellung>",
        shipping_product=args.shipping_product,
        tracking_number=args.tracking_number,
        dhl_cart_id=args.dhl_cart_id,
    ).payload

    existing = None
    if not args.skip_invoiz_check:
        client = InvoizClient(settings)
        invoice_matches = find_invoice_matches(client, order)
        invoice_numbers = [match["number"] for match in invoice_matches if match.get("number")]
        existing = {
            "invoices": invoice_matches,
            "expenses": find_expense_matches(client, order, invoice_numbers),
        }

    print_json(
        {
            "ok": True,
            "order": summarize_order(order),
            "existing_invoiz_matches": existing,
            "invoice_draft": invoice_draft,
            "expense_draft": expense_draft,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
