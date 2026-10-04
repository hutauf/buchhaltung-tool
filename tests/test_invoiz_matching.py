from __future__ import annotations

import unittest
from datetime import UTC, datetime

from autobookkeeping.invoiz_matching import find_expense_matches, find_invoice_matches
from autobookkeeping.models import Address, EbayOrder


class FakeInvoizClient:
    def __init__(self, invoices=None, expenses=None, search_results=None):
        self.invoices = invoices or []
        self.expenses = expenses or []
        self.search_results = search_results or {}

    def list_invoices(self, limit=20, offset=0, search_text=""):
        data = self.search_results.get(("invoice", search_text), self.invoices if not search_text else [])
        return {"data": data[:limit]}

    def list_expenses(self, limit=20, offset=0, search_text=""):
        data = self.search_results.get(("expense", search_text), self.expenses if not search_text else [])
        return {"data": data[:limit]}


def projector_order() -> EbayOrder:
    return EbayOrder(
        order_id="00-00000-00001",
        created_at=datetime(2011, 6, 22, 5, 10, tzinfo=UTC),
        total_value=42.00,
        tracking_number="TEST-TRACKING-000001",
        shipping_address=Address(name="TESTKUNDE ALPHA", city="Teststadt"),
    )


class InvoizMatchingTests(unittest.TestCase):
    def test_falls_back_to_recent_invoices_when_search_endpoint_misses(self):
        invoice = {
            "id": 900001,
            "number": "0905",
            "date": "2011-06-22T00:00:00.000Z",
            "totalGross": 42.00,
            "customerData": {"name": "TESTKUNDE ALPHA", "number": "00-00000-00001"},
        }

        matches = find_invoice_matches(FakeInvoizClient(invoices=[invoice]), projector_order())

        self.assertEqual([900001], [match["id"] for match in matches])
        self.assertEqual("field:00-00000-00001", matches[0]["matchedBy"])

    def test_matches_unlinked_manual_invoice_by_customer_amount_and_date(self):
        invoice = {
            "id": 900001,
            "number": "0905",
            "date": "2011-06-22T00:00:00.000Z",
            "totalGross": 42.00,
            "customerData": {"name": "TESTKUNDE ALPHA", "number": "10001"},
        }

        matches = find_invoice_matches(FakeInvoizClient(invoices=[invoice]), projector_order())

        self.assertEqual("customer+amount+date", matches[0]["matchedBy"])

    def test_deduplicates_direct_and_fallback_invoice_matches(self):
        invoice = {
            "id": 900001,
            "number": "0905",
            "date": "2011-06-22T00:00:00.000Z",
            "totalGross": 42.00,
            "customerData": {"name": "TESTKUNDE ALPHA", "number": "00-00000-00001"},
        }
        client = FakeInvoizClient(
            invoices=[invoice],
            search_results={("invoice", "00-00000-00001"): [invoice]},
        )

        matches = find_invoice_matches(client, projector_order())

        self.assertEqual(1, len(matches))

    def test_expense_fallback_uses_verified_invoice_number(self):
        expense = {
            "id": 800001,
            "date": "2011-06-22T00:00:00.000Z",
            "priceTotal": 3.00,
            "payee": "DHL",
            "description": "DHL Paket - Rechnung 0905",
        }

        matches = find_expense_matches(
            FakeInvoizClient(expenses=[expense]),
            projector_order(),
            invoice_numbers=["0905"],
        )

        self.assertEqual([800001], [match["id"] for match in matches])

    def test_does_not_match_short_srn_inside_another_order_number(self):
        invoice = {
            "id": 900004,
            "number": "0906",
            "date": "2011-08-26T00:00:00.000Z",
            "totalGross": 130.0,
            "customerData": {"name": "TESTKUNDE BETA", "number": "00-00000-00585"},
        }
        order = projector_order()
        order.sales_record_number = "585"

        client = FakeInvoizClient(
            search_results={("invoice", "585"): [invoice]},
        )

        matches = find_invoice_matches(client, order)

        self.assertEqual([], matches)


if __name__ == "__main__":
    unittest.main()
