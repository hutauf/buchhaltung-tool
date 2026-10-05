from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class Address:
    name: str = ""
    street1: str = ""
    street2: str = ""
    postal_code: str = ""
    city: str = ""
    country: str = ""
    country_iso: str = ""

    @property
    def street(self) -> str:
        return "\n".join(part for part in [self.street1, self.street2] if part)


@dataclass(slots=True)
class EbayOrderItem:
    title: str
    quantity: int = 1
    price: float = 0.0
    currency: str = "EUR"
    item_id: str | None = None
    transaction_id: str | None = None


@dataclass(slots=True)
class EbayOrder:
    order_id: str
    sales_record_number: str | None = None
    order_status: str | None = None
    order_id_aliases: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    paid_at: datetime | None = None
    shipped_at: datetime | None = None
    buyer_username: str | None = None
    total_value: float = 0.0
    currency: str = "EUR"
    shipping_cost: float = 0.0
    shipping_service: str | None = None
    tracking_number: str | None = None
    tracking_carrier: str | None = None
    shipping_address: Address = field(default_factory=Address)
    items: list[EbayOrderItem] = field(default_factory=list)

    @property
    def is_shipped(self) -> bool:
        return self.shipped_at is not None or bool(self.tracking_number)

    @property
    def item_total(self) -> float:
        return round(sum(item.price * item.quantity for item in self.items), 2)


@dataclass(slots=True)
class DhlMailCandidate:
    uid: str
    subject: str
    sender: str
    date: str
    tracking_numbers: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
