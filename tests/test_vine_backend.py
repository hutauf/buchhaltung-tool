from __future__ import annotations

import unittest

from autobookkeeping.models import Address
from autobookkeeping.vine_backend import (
    VineRecord,
    format_buyer_address,
    inventory_records,
    match_recommendation,
    sold_usage_status,
)


def record(asin: str, name: str, statuses: list[str], date: str = "2011-01-01") -> VineRecord:
    return VineRecord(
        asin=asin,
        last_update_time=1,
        value={"name": name, "usageStatus": statuses, "date": date},
    )


class VineBackendTests(unittest.TestCase):
    def test_inventory_filter_requires_lager(self):
        records = [
            record("B000000001", "Im Lager", ["Lager"]),
            record("B000000002", "Schon verkauft", ["verkauft"]),
        ]

        self.assertEqual(["B000000001"], [item.asin for item in inventory_records(records)])

    def test_sold_status_replaces_exclusive_status_and_keeps_defekt(self):
        result = sold_usage_status(["Lager", "defekt", "betriebliche Nutzung"])

        self.assertEqual(["verkauft", "defekt"], result)

    def test_formats_multiline_buyer_address_with_order_id(self):
        address = Address(
            name="Erika Beispiel",
            street1="Musterstraße 12",
            street2="Hinterhaus",
            postal_code="12345",
            city="Musterstadt",
        )

        result = format_buyer_address(address, "00-00000-00006")

        self.assertEqual(
            "Erika Beispiel\nMusterstraße 12\nHinterhaus\n12345 Musterstadt\n"
            "eBay-Bestellung 00-00000-00006",
            result,
        )

    def test_returns_only_one_candidate_for_clear_model_match(self):
        records = [
            record(
                "B000000001",
                "TESTMARKE HDMI KVM Switch 2 PC 2 Monitore 8K60Hz 4K240Hz 4 USB 3.0 Ports",
                ["Lager"],
            ),
            record(
                "B000000002",
                "TESTMARKE Tablet Halterung Auto für iPad und Nintendo Switch",
                ["Lager"],
            ),
            record(
                "B000000003",
                "DEMOMARKE USB-C Dockingstation für zwei Monitore HDMI USB 3.0",
                ["Lager"],
            ),
        ]

        result = match_recommendation(
            records,
            "TESTMARKE HDMI Dual Monitor KVM Switch 2 in 2 out für 2 Monitore 8K 60Hz 4x USB 3,0",
        )

        self.assertEqual("unique", result["status"])
        self.assertEqual(["B000000001"], [item["ASIN"] for item in result["candidates"]])
        self.assertIn("TESTMARKE HDMI KVM Switch", result["candidates"][0]["name"])

    def test_returns_all_plausible_candidates_when_names_are_ambiguous(self):
        records = [
            record("B000000001", "ACME X200 Mini Luftreiniger Weiß", ["Lager"], "2010-01-01"),
            record("B000000002", "ACME X200 Mini Luftreiniger Schwarz", ["Lager"], "2011-01-01"),
        ]

        result = match_recommendation(records, "ACME X200 Mini Luftreiniger")

        self.assertEqual("ambiguous", result["status"])
        self.assertEqual(2, len(result["candidates"]))

    def test_returns_not_found_for_dummy_title(self):
        records = [record("B000000001", "TESTMARKE HDMI KVM Switch 8K", ["Lager"])]

        result = match_recommendation(records, "Tolles Produkt Sonderangebot")

        self.assertEqual("not_found", result["status"])
        self.assertEqual([], result["candidates"])


if __name__ == "__main__":
    unittest.main()
