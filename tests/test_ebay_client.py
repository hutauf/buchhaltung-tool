from __future__ import annotations

import unittest
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from autobookkeeping.ebay_client import _coalesce_orders, _parse_order
from autobookkeeping.models import EbayOrder


class EbayClientTests(unittest.TestCase):
    def test_parses_sales_record_number_and_order_status(self):
        node = ET.fromstring(
            """
            <Order xmlns="urn:ebay:apis:eBLBaseComponents">
              <OrderID>00-00000-00005</OrderID>
              <OrderStatus>Completed</OrderStatus>
              <ShippingDetails>
                <SellingManagerSalesRecordNumber>123</SellingManagerSalesRecordNumber>
              </ShippingDetails>
              <Total currencyID="EUR">11.19</Total>
            </Order>
            """
        )

        order = _parse_order(node)

        self.assertEqual("123", order.sales_record_number)
        self.assertEqual("Completed", order.order_status)

    def test_coalesces_unpaid_and_paid_order_ids_by_srn(self):
        unpaid = EbayOrder(
            order_id="000000000001-00000000000001",
            sales_record_number="123",
            created_at=datetime(2011, 9, 22, tzinfo=UTC),
        )
        paid = EbayOrder(
            order_id="00-00000-00005",
            sales_record_number="123",
            created_at=datetime(2011, 9, 23, tzinfo=UTC),
            paid_at=datetime(2011, 9, 23, tzinfo=UTC),
        )

        orders = _coalesce_orders([unpaid, paid])

        self.assertEqual(1, len(orders))
        self.assertEqual("00-00000-00005", orders[0].order_id)
        self.assertEqual(["000000000001-00000000000001"], orders[0].order_id_aliases)


if __name__ == "__main__":
    unittest.main()
