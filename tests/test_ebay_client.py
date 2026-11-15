from __future__ import annotations

import unittest
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from autobookkeeping.ebay_client import _coalesce_orders, _parse_order
from autobookkeeping.models import EbayOrder


class EbayClientTests(unittest.TestCase):
    def international_order(self):
        return ET.fromstring('''<Order xmlns="urn:ebay:apis:eBLBaseComponents">
          <OrderID>synthetic-international</OrderID>
          <PaidTime>2025-01-02T12:00:00Z</PaidTime>
          <Subtotal currencyID="EUR">20.00</Subtotal>
          <Total currencyID="EUR">32.80</Total>
          <ShippingServiceSelected><ShippingService>DE_eBayIntermediatedInternationalPriorityShippingIntraEU</ShippingService>
            <ShippingServiceCost currencyID="EUR">11.50</ShippingServiceCost></ShippingServiceSelected>
          <MultiLegShippingDetails><SellerShipmentToLogisticsProvider><ShippingServiceDetails>
            <ShippingService>DE_DHLPaket</ShippingService><TotalShippingCost currencyID="EUR">4.50</TotalShippingCost>
          </ShippingServiceDetails></SellerShipmentToLogisticsProvider></MultiLegShippingDetails>
          <MonetaryDetails><Payments>
            <Payment><PaymentStatus>Succeeded</PaymentStatus><Payee>eBay</Payee><PaymentAmount currencyID="EUR">8.30</PaymentAmount></Payment>
            <Payment><PaymentStatus>Succeeded</PaymentStatus><Payee>synthetic-seller</Payee><PaymentAmount currencyID="EUR">24.50</PaymentAmount></Payment>
          </Payments></MonetaryDetails>
        </Order>''')

    def test_international_seller_amount_excludes_ebay_shipping_and_tax(self):
        order = _parse_order(self.international_order())
        self.assertEqual((24.5, 4.5, 'DE_DHLPaket'),
                         (order.total_value, order.shipping_cost, order.shipping_service))

    def test_international_amounts_fail_closed_on_missing_or_conflicting_evidence(self):
        ns = {'e': 'urn:ebay:apis:eBLBaseComponents'}
        for path, text, currency in [
            ('e:Subtotal', 'not-money', None), ('e:Subtotal', 'NaN', None),
            ('e:Subtotal', '20.001', None), ('e:Subtotal', '20.00', 'USD'),
            ('e:MonetaryDetails/e:Payments/e:Payment[2]/e:PaymentAmount', '21.50', None),
            ('e:MonetaryDetails/e:Payments/e:Payment[2]/e:PaymentStatus', 'Pending', None),
            ('e:MonetaryDetails/e:Payments/e:Payment[2]/e:Payee', '', None),
        ]:
            with self.subTest(path=path, text=text, currency=currency):
                node = self.international_order(); field = node.find(path, ns); field.text = text
                if currency: field.set('currencyID', currency)
                with self.assertRaises(ValueError): _parse_order(node)
        for path in ['e:Subtotal', 'e:MultiLegShippingDetails', 'e:MonetaryDetails']:
            node = self.international_order(); node.remove(node.find(path, ns))
            with self.subTest(missing=path), self.assertRaises(ValueError): _parse_order(node)

    def test_unpaid_international_order_remains_unpaid_without_payment_allocation(self):
        ns = {'e': 'urn:ebay:apis:eBLBaseComponents'}
        node = self.international_order()
        for path in ['e:PaidTime', 'e:MonetaryDetails']: node.remove(node.find(path, ns))
        order = _parse_order(node)
        self.assertIsNone(order.paid_at)
        self.assertEqual(24.5, order.total_value)

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
