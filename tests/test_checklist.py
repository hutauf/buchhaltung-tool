from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from autobookkeeping.checklist import ChecklistStore


class ChecklistStoreTests(unittest.TestCase):
    def test_ignores_optional_none_status(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChecklistStore(Path(directory) / "checklist.json")

            item = store.upsert("00-00000-00001", {"status": None, "invoice_id": 900001})

        self.assertEqual("rechnung_angelegt", item["status"])

    def test_preserves_private_status_without_bookkeeping_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChecklistStore(Path(directory) / "checklist.json")

            item = store.upsert(
                "00-00000-00002",
                {"status": "privat", "note": "Privatverkauf"},
            )
            refreshed = store.upsert("00-00000-00002", {"status": None})

        self.assertEqual("privat", item["status"])
        self.assertEqual("privat", refreshed["status"])
        self.assertEqual("Privatverkauf", refreshed["note"])

    def test_records_multiple_vine_sales_for_one_order(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChecklistStore(Path(directory) / "checklist.json")
            store.record_vine_sale(
                "00-00000-00003",
                {
                    "asin": "B000000001",
                    "product_title": "Erstes Produkt",
                    "sale_price": 35.5,
                    "sale_date": "16.07.2011",
                    "verified": True,
                },
            )
            item = store.record_vine_sale(
                "00-00000-00003",
                {
                    "asin": "B000000002",
                    "product_title": "Zweites Produkt",
                    "sale_price": 4.5,
                    "sale_date": "16.07.2011",
                    "verified": True,
                },
            )

        self.assertEqual(2, len(item["vine_sales"]))
        self.assertNotIn("vine_asin", item)

    def test_clear_invoice_removes_invoice_fields_and_reopens_order(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChecklistStore(Path(directory) / "checklist.json")
            store.upsert(
                "00-00000-00004",
                {
                    "invoice_id": 900002,
                    "invoice_number": "draft-number",
                    "invoice_total": 18.7,
                    "status": "rechnung_angelegt",
                },
            )

            item = store.clear_invoice("00-00000-00004", expected_invoice_id=900002)

        self.assertEqual("offen", item["status"])
        self.assertNotIn("invoice_id", item)
        self.assertNotIn("invoice_number", item)
        self.assertNotIn("invoice_total", item)

    def test_merges_unpaid_and_paid_order_ids_by_sales_record_number(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChecklistStore(Path(directory) / "checklist.json")
            unpaid = store.upsert(
                "000000000001-00000000000001",
                {
                    "status": "offen",
                    "sales_record_number": "123",
                    "order_status": "Active",
                },
            )
            paid = store.upsert(
                "00-00000-00005",
                {
                    "status": "rechnung_angelegt",
                    "invoice_id": 900003,
                    "sales_record_number": "123",
                    "paid_at": "2011-09-23T14:52:49+00:00",
                    "order_status": "Completed",
                },
            )
            old_id_lookup = store.find("000000000001-00000000000001")
            srn_lookup = store.find(sales_record_number="123")

        self.assertEqual("offen", unpaid["status"])
        self.assertEqual("00-00000-00005", paid["order_id"])
        self.assertEqual(["000000000001-00000000000001"], paid["order_id_aliases"])
        self.assertEqual("rechnung_angelegt", paid["status"])
        self.assertEqual(old_id_lookup, srn_lookup)

    def test_unpaid_alias_update_does_not_demote_paid_canonical_order(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ChecklistStore(Path(directory) / "checklist.json")
            store.upsert(
                "old-unpaid-id",
                {
                    "status": "offen",
                    "sales_record_number": "456",
                },
            )
            store.upsert(
                "new-paid-id",
                {
                    "status": "rechnung_angelegt",
                    "invoice_id": 1,
                    "sales_record_number": "456",
                    "paid_at": "2011-09-23T14:52:49+00:00",
                },
            )
            refreshed = store.upsert(
                "old-unpaid-id",
                {
                    "status": "offen",
                    "sales_record_number": "456",
                },
            )

        self.assertEqual("new-paid-id", refreshed["order_id"])
        self.assertEqual("rechnung_angelegt", refreshed["status"])


if __name__ == "__main__":
    unittest.main()
