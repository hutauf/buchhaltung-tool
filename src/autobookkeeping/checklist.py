from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


from autobookkeeping.workspace import data_root
from dataclasses import field

def default_checklist():
    return data_root() / "bookkeeping_checklist.json.enc"

STATUSES = {
    "offen",
    "privat",
    "rechnung_angelegt",
    "rechnung_abgeschlossen",
    "ausgabe_angelegt",
    "ok",
}


@dataclass(slots=True)
class ChecklistStore:
    path: Path = field(default_factory=default_checklist)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "items": []}
        if self.path.suffix == ".enc":
            from autobookkeeping.archive import Archive, unseal
            return json.loads(unseal(Archive(self.path.parent).unlock(), self.path.read_bytes(), "bookkeeping_checklist.json"))
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, data: dict[str, Any]) -> None:
        if self.path.suffix == ".enc":
            from autobookkeeping.archive import Archive, atomic, encoded, seal
            atomic(self.path, seal(Archive(self.path.parent).unlock(), encoded(data), "bookkeeping_checklist.json"))
        else:
            self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def find(
        self,
        order_id: str | None = None,
        sales_record_number: str | None = None,
    ) -> dict[str, Any] | None:
        data = self.load()
        return _find_item(data.get("items", []), order_id, sales_record_number)

    def upsert(self, order_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        items = data.setdefault("items", [])
        sales_record_number = _identifier(updates.get("sales_record_number"))
        item = _find_item(items, order_id, sales_record_number)
        if item is None:
            item = {
                "order_id": order_id,
                "status": "offen",
                "created_at": _now(),
            }
            items.append(item)
        else:
            _remember_order_id(
                item,
                order_id,
                promote=_incoming_representation_is_paid(updates),
            )
        _remember_order_aliases(item, updates.get("order_id_aliases"))
        if updates.get("status") is not None and updates["status"] not in STATUSES:
            raise ValueError(f"Invalid checklist status: {updates['status']}")
        normalized_updates = dict(updates)
        normalized_updates.pop("order_id_aliases", None)
        if sales_record_number:
            normalized_updates["sales_record_number"] = sales_record_number
        item.update({key: value for key, value in normalized_updates.items() if value is not None})
        item["updated_at"] = _now()
        item["status"] = _derive_status(item)
        self.save(data)
        return item

    def record_vine_sale(
        self,
        order_id: str,
        sale: dict[str, Any],
        sales_record_number: str | None = None,
    ) -> dict[str, Any]:
        """Record one verified Vine sale without losing other items in the eBay order."""
        data = self.load()
        items = data.setdefault("items", [])
        item = _find_item(items, order_id, sales_record_number)
        if item is None:
            item = {
                "order_id": order_id,
                "status": "offen",
                "created_at": _now(),
            }
            items.append(item)
        else:
            _remember_order_id(item, order_id, promote=True)
        if sales_record_number:
            item["sales_record_number"] = _identifier(sales_record_number)

        sales = list(item.get("vine_sales") or [])
        sales = [entry for entry in sales if entry.get("asin") != sale.get("asin")]
        sales.append({key: value for key, value in sale.items() if value is not None})
        item["vine_sales"] = sales

        scalar_fields = ("vine_asin", "vine_sale_price", "vine_sale_date", "vine_sale_verified")
        if len(sales) == 1:
            only_sale = sales[0]
            item.update(
                {
                    "vine_asin": only_sale.get("asin"),
                    "vine_sale_price": only_sale.get("sale_price"),
                    "vine_sale_date": only_sale.get("sale_date"),
                    "vine_sale_verified": only_sale.get("verified"),
                }
            )
        else:
            for field in scalar_fields:
                item.pop(field, None)

        item["updated_at"] = _now()
        item["status"] = _derive_status(item)
        self.save(data)
        return item

    def clear_invoice(
        self,
        order_id: str,
        expected_invoice_id: int | None = None,
        sales_record_number: str | None = None,
    ) -> dict[str, Any]:
        """Remove draft/final invoice fields after an explicitly requested replacement."""
        data = self.load()
        item = _find_item(data.setdefault("items", []), order_id, sales_record_number)
        if item is None:
            raise ValueError(f"Checklist entry not found: {order_id}")
        if expected_invoice_id is not None and item.get("invoice_id") != expected_invoice_id:
            raise ValueError(
                f"Checklist invoice mismatch for {order_id}: "
                f"expected {expected_invoice_id}, found {item.get('invoice_id')}"
            )

        for field in ("invoice_id", "invoice_number", "invoice_locked_at", "invoice_total"):
            item.pop(field, None)
        item["status"] = "ausgabe_angelegt" if item.get("expense_id") else "offen"
        item["updated_at"] = _now()
        self.save(data)
        return item


def _find_item(
    items: list[dict[str, Any]],
    order_id: str | None,
    sales_record_number: str | None,
) -> dict[str, Any] | None:
    wanted_order_id = _identifier(order_id)
    wanted_srn = _identifier(sales_record_number)
    for item in items:
        item_order_id = _identifier(item.get("order_id"))
        aliases = {
            _identifier(value)
            for value in item.get("order_id_aliases", [])
            if _identifier(value)
        }
        item_srn = _identifier(item.get("sales_record_number"))
        if wanted_order_id and (wanted_order_id == item_order_id or wanted_order_id in aliases):
            return item
        if wanted_srn and wanted_srn == item_srn:
            return item
    return None


def _derive_status(item: dict[str, Any]) -> str:
    if item.get("invoice_id") and item.get("invoice_number") and item.get("expense_id"):
        return "ok"
    if item.get("expense_id"):
        return "ausgabe_angelegt"
    if item.get("invoice_number") or item.get("invoice_locked_at"):
        return "rechnung_abgeschlossen"
    if item.get("invoice_id"):
        return "rechnung_angelegt"
    return item.get("status", "offen")


def _identifier(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _incoming_representation_is_paid(updates: dict[str, Any]) -> bool:
    if any(
        updates.get(field)
        for field in (
            "paid_at",
            "invoice_id",
            "invoice_number",
            "invoice_locked_at",
            "expense_id",
            "vine_asin",
        )
    ):
        return True
    return updates.get("status") in {
        "rechnung_angelegt",
        "rechnung_abgeschlossen",
        "ausgabe_angelegt",
        "ok",
    }


def _remember_order_id(item: dict[str, Any], order_id: str, promote: bool) -> None:
    incoming = _identifier(order_id)
    current = _identifier(item.get("order_id"))
    aliases = [
        _identifier(value)
        for value in item.get("order_id_aliases", [])
        if _identifier(value)
    ]
    if incoming and incoming != current:
        if promote and current:
            aliases.append(current)
            item["order_id"] = incoming
        else:
            aliases.append(incoming)
    aliases = list(dict.fromkeys(value for value in aliases if value and value != item.get("order_id")))
    if aliases:
        item["order_id_aliases"] = aliases
    else:
        item.pop("order_id_aliases", None)


def _remember_order_aliases(item: dict[str, Any], aliases: Any) -> None:
    if not aliases:
        return
    current = _identifier(item.get("order_id"))
    stored = [
        _identifier(value)
        for value in item.get("order_id_aliases", [])
        if _identifier(value)
    ]
    for value in aliases:
        alias = _identifier(value)
        if alias and alias != current:
            stored.append(alias)
    stored = list(dict.fromkeys(value for value in stored if value and value != current))
    if stored:
        item["order_id_aliases"] = stored


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
