from __future__ import annotations

import json
import math
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import httpx

from autobookkeeping.config import Settings
from autobookkeeping.models import Address


EXCLUSIVE_USAGE_STATUSES = {
    "storniert",
    "verkauft",
    "entsorgt",
    "Privatentnahme",
    "Lager",
    "betriebliche Nutzung",
}

_STOPWORDS = {
    "der",
    "die",
    "das",
    "ein",
    "eine",
    "einer",
    "und",
    "oder",
    "mit",
    "fur",
    "von",
    "aus",
    "zum",
    "zur",
    "neu",
    "ovp",
    "new",
    "the",
    "with",
    "for",
}


@dataclass(slots=True)
class VineRecord:
    asin: str
    last_update_time: int | None
    value: dict[str, Any]


class VineBackendClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.vine_backend_token:
            raise RuntimeError("VINE_BACKEND_TOKEN fehlt")
        self.url = settings.vine_backend_url
        self.token = settings.vine_backend_token

    def get_all(self) -> list[VineRecord]:
        return self._parse_records(self._post({"token": self.token, "request": "get_all"}))

    def get_asins(self, asins: list[str]) -> list[VineRecord]:
        payload = self._post(
            {"token": self.token, "request": "get_asin", "payload": asins}
        )
        return self._parse_records(payload)

    def update_asin(
        self,
        asin: str,
        value: dict[str, Any],
        timestamp: int | None = None,
    ) -> dict[str, Any]:
        if timestamp is None:
            timestamp = int(time.time())
        payload = {
            "token": self.token,
            "request": "update_asin",
            "payload": [
                {
                    "ASIN": asin,
                    "timestamp": timestamp,
                    "value": json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                }
            ],
        }
        return self._post(payload)

    def _parse_records(self, payload: dict[str, Any]) -> list[VineRecord]:
        records = []
        for row in payload.get("data", []):
            raw_value = row.get("value") or "{}"
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError:
                value = {"_parse_error": raw_value}
            asin = str(row.get("ASIN") or value.get("ASIN") or "")
            records.append(
                VineRecord(
                    asin=asin,
                    last_update_time=row.get("last_update_time"),
                    value=value,
                )
            )
        return records

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(self.url, json=payload, timeout=60)
        if response.is_error:
            raise RuntimeError(
                f"Vine backend failed: {response.status_code} {response.text[:1000]}"
            )
        return response.json()


def sold_records(records: list[VineRecord]) -> list[VineRecord]:
    return [record for record in records if "verkauft" in record.value.get("usageStatus", [])]


def inventory_records(records: list[VineRecord]) -> list[VineRecord]:
    """Return only products which are currently available in Vine inventory."""
    return [record for record in records if "Lager" in record.value.get("usageStatus", [])]


def sold_usage_status(current_statuses: list[Any]) -> list[str]:
    """Mirror the frontend's mutually-exclusive status handling and retain add-ons."""
    retained = list(
        dict.fromkeys(
            str(status)
            for status in current_statuses
            if str(status) not in EXCLUSIVE_USAGE_STATUSES
        )
    )
    return ["verkauft", *retained]


def format_buyer_address(address: Address, order_id: str) -> str:
    """Format the existing multiline buyerAddress field used by the Vine frontend."""
    street_lines = [part for part in (address.street1, address.street2) if part]
    city_line = " ".join(part for part in (address.postal_code, address.city) if part)
    return "\n".join(
        part
        for part in (
            address.name,
            *street_lines,
            city_line,
            f"eBay-Bestellung {order_id}",
        )
        if part
    )


def candidate_matches(
    records: list[VineRecord],
    title: str,
    sale_price: float | None = None,
) -> list[dict[str, Any]]:
    """Rank title matches using inventory-relative token weights.

    ``sale_price`` remains part of the public signature for existing callers, but is
    intentionally not used as evidence: an eBay auction price need not resemble ETV,
    Teilwert, or any prior Vine sale price.
    """
    del sale_price
    query_tokens = _tokens(title)
    if not query_tokens:
        return []

    tokenized_records = [
        (record, _tokens(str(record.value.get("name") or ""))) for record in records
    ]
    document_frequency = Counter(
        token for _, tokens in tokenized_records for token in set(tokens)
    )
    record_count = max(len(tokenized_records), 1)
    query_set = set(query_tokens)
    weights = {
        token: _token_weight(token, document_frequency[token], record_count)
        for token in query_set
    }
    total_query_weight = sum(weights.values()) or 1.0
    normalized_title = " ".join(query_tokens)
    candidates = []

    for record, name_tokens in tokenized_records:
        name_set = set(name_tokens)
        matched_query_tokens = {
            query_token
            for query_token in query_set
            if any(_tokens_match(query_token, name_token) for name_token in name_set)
        }
        if not matched_query_tokens:
            continue

        matched_weight = sum(weights[token] for token in matched_query_tokens)
        coverage = matched_weight / total_query_weight
        precision = len(matched_query_tokens) / max(len(query_set), 1)
        sequence = SequenceMatcher(None, normalized_title, " ".join(name_tokens)).ratio()
        strong_matches = sorted(
            token for token in matched_query_tokens if _is_identifier(token)
        )
        brand_match = bool(query_tokens and query_tokens[0] in name_set)

        score = 65 * coverage + 20 * sequence + 10 * precision
        if strong_matches:
            score += min(10, 4 + 2 * len(strong_matches))
        if brand_match:
            score += 5
        score = round(min(score, 100.0), 1)

        reasons = []
        if brand_match:
            reasons.append(f"Marke/Anfangsbegriff: {query_tokens[0]}")
        if strong_matches:
            reasons.append(f"Modellmerkmale: {', '.join(strong_matches[:6])}")
        reasons.append(
            f"Gemeinsame Begriffe: {', '.join(sorted(matched_query_tokens)[:10])}"
        )

        value = record.value
        candidates.append(
            {
                "ASIN": record.asin,
                "score": score,
                "confidence": _confidence(score),
                "name": value.get("name"),
                "orderDate": value.get("date"),
                "ordernumber": value.get("ordernumber"),
                "etv": value.get("etv"),
                "teilwert": value.get("teilwert"),
                "teilwert_v2": value.get("teilwert_v2"),
                "salePrice": value.get("salePrice"),
                "saleDate": value.get("saleDate"),
                "usageStatus": value.get("usageStatus", []),
                "reasons": reasons,
            }
        )

    return sorted(
        candidates,
        key=lambda item: (
            item["score"],
            _oldest_first_value(item.get("orderDate")),
        ),
        reverse=True,
    )


def match_recommendation(
    records: list[VineRecord],
    title: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Return one clear hit, an ambiguity set, or an explicit not-found result."""
    inventory = inventory_records(records)
    ranked = candidate_matches(inventory, title)
    if not ranked or ranked[0]["score"] < 45:
        return {
            "status": "not_found",
            "message": "Kein ausreichend plausibler Treffer im Vine-Lager gefunden.",
            "candidates": [],
        }

    top_score = ranked[0]["score"]
    second_score = ranked[1]["score"] if len(ranked) > 1 else 0
    if top_score >= 75 and top_score - second_score >= 15:
        return {
            "status": "unique",
            "message": "Ein eindeutiger Vine-Kandidat wurde gefunden.",
            "candidates": [ranked[0]],
        }

    plausible = [candidate for candidate in ranked if candidate["score"] >= max(35, top_score - 25)]
    return {
        "status": "ambiguous",
        "message": "Mehrere Vine-Produkte sind plausibel; eine Auswahl ist erforderlich.",
        "candidates": plausible[:limit],
    }


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    ascii_like = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    parts = re.findall(r"[a-z0-9]+", ascii_like)
    return [
        part
        for part in parts
        if part not in _STOPWORDS and (len(part) >= 3 or _is_identifier(part))
    ]


def _token_weight(token: str, frequency: int, record_count: int) -> float:
    weight = 1.0 + math.log((record_count + 1) / (frequency + 1))
    if _is_identifier(token):
        weight *= 1.8
    elif len(token) >= 7:
        weight *= 1.25
    return weight


def _is_identifier(token: str) -> bool:
    has_digit = any(character.isdigit() for character in token)
    has_letter = any(character.isalpha() for character in token)
    return (has_digit and has_letter) or (has_digit and len(token) >= 2)


def _tokens_match(query_token: str, name_token: str) -> bool:
    if query_token == name_token:
        return True
    if _is_identifier(query_token) and _is_identifier(name_token):
        shorter, longer = sorted((query_token, name_token), key=len)
        return len(shorter) >= 2 and shorter in longer
    if min(len(query_token), len(name_token)) >= 5:
        return (
            query_token.startswith(name_token)
            or name_token.startswith(query_token)
        ) and abs(len(query_token) - len(name_token)) <= 2
    return False


def _confidence(score: float) -> str:
    if score >= 75:
        return "hoch"
    if score >= 45:
        return "mittel"
    return "niedrig"


def _oldest_first_value(value: Any) -> str:
    # Reverse sorting is used above, so invert digits to prefer older dates only as tie-breaker.
    text = str(value or "9999-99-99")
    return "".join(
        str(9 - int(character)) if character.isdigit() else character
        for character in text
    )
