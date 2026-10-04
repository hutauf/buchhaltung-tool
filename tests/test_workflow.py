from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from autobookkeeping.models import Address, EbayOrder, EbayOrderItem
from autobookkeeping.workflow import allocate_equal_prices, build_invoice_draft


class WorkflowTests(unittest.TestCase):
    def test_equal_allocation_is_cent_exact(self):
        prices = allocate_equal_prices(11.01, 14)

        self.assertEqual([0.79] * 9 + [0.78] * 5, prices)
        self.assertEqual(11.01, round(sum(prices), 2))

    def test_equal_allocation_rejects_empty_lot(self):
        with self.assertRaises(ValueError):
            allocate_equal_prices(11.01, 0)

    def test_invoice_reuses_existing_customer_id_without_customer_data(self):
        order = EbayOrder(
            order_id="00-00000-00004",
            paid_at=datetime(2011, 8, 27, tzinfo=timezone.utc),
            items=[EbayOrderItem("Konvolut", price=11.01)],
            shipping_cost=7.69,
            shipping_address=Address(name="TESTKUNDE GAMMA"),
        )
        settings = SimpleNamespace(
            invoiz_pay_condition_id=700001,
            bookkeeping_vat_percent=0,
            bookkeeping_price_kind="gross",
            shipping_article_title="Versandkosten",
            invoice_intro="Danke",
            invoice_conclusion="",
        )

        payload = build_invoice_draft(order, settings, customer_id=600001).payload

        self.assertEqual(600001, payload["customerId"])
        self.assertNotIn("customerData", payload)

    def test_invoice_can_include_zero_shipping_position(self):
        order = EbayOrder(
            order_id="TEST-KA-000001",
            paid_at=datetime(2011, 9, 14, tzinfo=timezone.utc),
            shipping_cost=0.0,
            shipping_service="Versand vom Käufer direkt über Kleinanzeigen bezahlt",
            items=[EbayOrderItem("TESTMARKE", price=12.0)],
        )
        settings = SimpleNamespace(
            invoiz_pay_condition_id=700001,
            bookkeeping_vat_percent=0,
            bookkeeping_price_kind="gross",
            shipping_article_title="Versandkosten",
            invoice_intro="Danke",
            invoice_conclusion="",
        )

        payload = build_invoice_draft(
            order,
            settings,
            source_label="Kleinanzeigen",
            source_reference=order.order_id,
            include_zero_shipping=True,
        ).payload

        self.assertEqual(2, len(payload["articles"]))
        self.assertEqual("Versandkosten", payload["articles"][1]["title"])
        self.assertEqual(0.0, payload["articles"][1]["price"])
        self.assertEqual(
            "Versand vom Käufer direkt über Kleinanzeigen bezahlt",
            payload["articles"][1]["description"],
        )

    def test_invoice_omits_missing_customer_address_fields(self):
        order = EbayOrder(
            order_id="TEST-KA-000001",
            shipping_address=Address(name="TESTKUNDE DELTA"),
            items=[EbayOrderItem("TESTMARKE", price=12.0)],
        )
        settings = SimpleNamespace(
            invoiz_pay_condition_id=700001,
            bookkeeping_vat_percent=0,
            bookkeeping_price_kind="gross",
            shipping_article_title="Versandkosten",
            invoice_intro="Danke",
            invoice_conclusion="",
        )

        payload = build_invoice_draft(order, settings).payload

        self.assertNotIn("street", payload["customerData"])
        self.assertNotIn("zipCode", payload["customerData"])
        self.assertNotIn("city", payload["customerData"])


if __name__ == "__main__":
    unittest.main()
