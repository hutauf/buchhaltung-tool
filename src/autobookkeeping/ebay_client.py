from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

import httpx

from autobookkeeping.config import Settings
from autobookkeeping.models import Address, EbayOrder, EbayOrderItem


NS = {"e": "urn:ebay:apis:eBLBaseComponents"}


class EbayTradingClient:
    """Small read-only client for eBay Trading API Auth'n'Auth."""

    PROD_TRADING_URL = "https://api.ebay.com/ws/api.dll"
    SANDBOX_TRADING_URL = "https://api.sandbox.ebay.com/ws/api.dll"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.trading_url = self.SANDBOX_TRADING_URL if settings.ebay_sandbox else self.PROD_TRADING_URL

    def get_orders(self, days: int = 30, limit: int | None = 20, shipped_only: bool = False) -> list[EbayOrder]:
        if not 1 <= days <= 90 or limit is not None and limit < 1:
            raise ValueError('Abruf benötigt 1–90 Tage und ein positives Limit')
        orders = []; self.order_pages = []; self.orders_complete = False
        current = datetime.now(timezone.utc)
        self.order_window = {'from': (current-timedelta(days=days)+timedelta(minutes=2)).isoformat(),
                             'to': (current-timedelta(minutes=2)).isoformat()}
        entries = min(limit or 100, 100)
        for page in range(1, 1001):
            root = self._call('GetOrders', self._get_orders_xml(days=days, limit=entries, page=page,
                               window=self.order_window if limit is None or days>30 else None))
            returned_page = _text(root, 'e:PaginationResult/e:PageNumber')
            if returned_page and int(returned_page) != page:
                raise RuntimeError('eBay lieferte eine andere Ergebnisseite')
            payload = getattr(self, 'last_response_bytes', None) or ET.tostring(root, encoding='utf-8')
            if payload in self.order_pages:
                raise RuntimeError('eBay wiederholt Ergebnisseiten; Abruf unvollständig')
            self.order_pages.append(payload)
            rows = [_parse_order(node) for node in _findall(root, './/e:Order')]
            orders.extend(rows)
            more = _text(root, 'e:HasMoreOrders')
            total_pages = _text(root, 'e:PaginationResult/e:TotalNumberOfPages')
            if more is None and total_pages is None and limit is None:
                raise RuntimeError('eBay liefert keine Vollständigkeitsangabe')
            has_more = more == 'true' if more is not None else page < int(total_pages or page)
            if total_pages is not None and has_more != (page < int(total_pages)):
                raise RuntimeError('eBay meldet widersprüchliche Seitenzahlen')
            if not has_more:
                self.orders_complete = True; break
            if not rows:
                raise RuntimeError('eBay meldet weitere, aber leere Ergebnisseiten')
            if limit is not None and len(_coalesce_orders(orders)) >= limit:
                break
        else:
            raise RuntimeError('Sicherheitslimit der eBay-Seiten erreicht; kein vollständiger Abruf')
        orders = _coalesce_orders(orders)
        if shipped_only:
            orders = [order for order in orders if order.is_shipped]
        return sorted(
            orders,
            key=lambda order: _timestamp(order.created_at),
            reverse=True,
        )[:limit]

    def get_order(self, order_id: str) -> EbayOrder:
        root = self._call("GetOrders", self._get_order_xml(order_id))
        orders = [_parse_order(node) for node in _findall(root, ".//e:Order")]
        if not orders:
            raise RuntimeError(f"eBay order not found: {order_id}")
        order = orders[0]
        if order.order_id != order_id and order_id not in order.order_id_aliases:
            order.order_id_aliases.append(order_id)
        return order

    def _call(self, call_name: str, body: str) -> ET.Element:
        if not self.settings.ebay_authnauth_token:
            raise RuntimeError("EBAY_AUTHNAUTH_TOKEN fehlt")

        headers = {
            "X-EBAY-API-COMPATIBILITY-LEVEL": self.settings.ebay_trading_compatibility_level,
            "X-EBAY-API-CALL-NAME": call_name,
            "X-EBAY-API-SITEID": self.settings.ebay_site_id,
            "X-EBAY-API-IAF-TOKEN": self.settings.ebay_authnauth_token,
            "Content-Type": "text/xml",
        }
        if self.settings.ebay_app_id:
            headers["X-EBAY-API-APP-NAME"] = self.settings.ebay_app_id
        if self.settings.ebay_dev_id:
            headers["X-EBAY-API-DEV-NAME"] = self.settings.ebay_dev_id
        if self.settings.ebay_cert_id:
            headers["X-EBAY-API-CERT-NAME"] = self.settings.ebay_cert_id

        response = httpx.post(self.trading_url, content=body.encode("utf-8"), headers=headers, timeout=30)
        response.raise_for_status()
        self.last_response_bytes = response.content
        root = ET.fromstring(response.content)
        ack = _text(root, "e:Ack")
        if ack not in {"Success", "Warning"}:
            raise RuntimeError(f"eBay Trading API {call_name} failed: {ack}: {_first_error(root)}")
        return root

    def _requester_credentials_xml(self) -> str:
        token = xml_escape(self.settings.ebay_authnauth_token)
        return f"<RequesterCredentials><eBayAuthToken>{token}</eBayAuthToken></RequesterCredentials>"

    def _get_orders_xml(self, days: int, limit: int, page: int = 1, window=None) -> str:
        # NumberOfDays is limited to 30; explicit creation windows allow 90.
        dates = (f'<CreateTimeFrom>{window["from"]}</CreateTimeFrom><CreateTimeTo>{window["to"]}</CreateTimeTo>'
                 if window else f'<NumberOfDays>{days}</NumberOfDays>')
        return f"""<?xml version="1.0" encoding="utf-8"?>
<GetOrdersRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <DetailLevel>ReturnAll</DetailLevel>
  {dates}
  <OrderRole>Seller</OrderRole>
  <OrderStatus>All</OrderStatus>
  <SortingOrder>Descending</SortingOrder>
  <Pagination>
    <EntriesPerPage>{limit}</EntriesPerPage>
    <PageNumber>{page}</PageNumber>
  </Pagination>
</GetOrdersRequest>"""

    def _get_order_xml(self, order_id: str) -> str:
        order_id = xml_escape(order_id)
        return f"""<?xml version="1.0" encoding="utf-8"?>
<GetOrdersRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <DetailLevel>ReturnAll</DetailLevel>
  <OrderRole>Seller</OrderRole>
  <OrderStatus>All</OrderStatus>
  <OrderIDArray>
    <OrderID>{order_id}</OrderID>
  </OrderIDArray>
</GetOrdersRequest>"""


def _parse_order(node: ET.Element) -> EbayOrder:
    total = node.find("e:Total", NS)
    shipping_cost = node.find("e:ShippingServiceSelected/e:ShippingServiceCost", NS)
    tracking = node.find(".//e:ShipmentTrackingDetails", NS)
    return EbayOrder(
        order_id=_text(node, "e:OrderID") or "",
        sales_record_number=_text(node, "e:ShippingDetails/e:SellingManagerSalesRecordNumber"),
        order_status=_text(node, "e:OrderStatus"),
        created_at=_parse_dt(_text(node, "e:CreatedTime")),
        paid_at=_parse_dt(_text(node, "e:PaidTime")),
        shipped_at=_parse_dt(_text(node, "e:ShippedTime")),
        buyer_username=_text(node, "e:BuyerUserID"),
        total_value=_to_float(total.text if total is not None else None),
        currency=total.attrib.get("currencyID", "EUR") if total is not None else "EUR",
        shipping_cost=_to_float(shipping_cost.text if shipping_cost is not None else None),
        shipping_service=_text(node, "e:ShippingServiceSelected/e:ShippingService"),
        tracking_number=_text(tracking, "e:ShipmentTrackingNumber"),
        tracking_carrier=_text(tracking, "e:ShippingCarrierUsed"),
        shipping_address=_parse_address(node.find("e:ShippingAddress", NS)),
        items=[_parse_item(tx) for tx in _findall(node, ".//e:Transaction")],
    )


def _coalesce_orders(orders: list[EbayOrder]) -> list[EbayOrder]:
    """Collapse unpaid/paid eBay representations that share one SRN."""
    grouped: dict[tuple[str, str], EbayOrder] = {}
    for order in orders:
        key = (
            "srn",
            order.sales_record_number,
        ) if order.sales_record_number else ("order", order.order_id)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = order
            continue

        winner, other = _prefer_order(existing, order)
        aliases = [
            *winner.order_id_aliases,
            winner.order_id if winner.order_id != other.order_id else "",
            *other.order_id_aliases,
            other.order_id,
        ]
        winner.order_id_aliases = _unique_nonempty(
            alias for alias in aliases if alias != winner.order_id
        )
        grouped[key] = winner
    return list(grouped.values())


def _prefer_order(first: EbayOrder, second: EbayOrder) -> tuple[EbayOrder, EbayOrder]:
    first_key = (
        first.paid_at is not None,
        first.shipped_at is not None,
        _timestamp(first.created_at),
    )
    second_key = (
        second.paid_at is not None,
        second.shipped_at is not None,
        _timestamp(second.created_at),
    )
    return (second, first) if second_key > first_key else (first, second)


def _unique_nonempty(values) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _timestamp(value: datetime | None) -> float:
    return value.timestamp() if value is not None else float("-inf")


def _parse_address(node: ET.Element | None) -> Address:
    return Address(
        name=_text(node, "e:Name") or "",
        street1=_text(node, "e:Street1") or "",
        street2=_text(node, "e:Street2") or "",
        postal_code=_text(node, "e:PostalCode") or "",
        city=_text(node, "e:CityName") or "",
        country=_text(node, "e:CountryName") or "",
        country_iso=_text(node, "e:Country") or "",
    )


def _parse_item(node: ET.Element) -> EbayOrderItem:
    item = node.find("e:Item", NS)
    price = node.find("e:TransactionPrice", NS)
    return EbayOrderItem(
        title=_text(item, "e:Title") or "Unbenannter Artikel",
        quantity=int(_text(node, "e:QuantityPurchased") or "1"),
        price=_to_float(price.text if price is not None else None),
        currency=price.attrib.get("currencyID", "EUR") if price is not None else "EUR",
        item_id=_text(item, "e:ItemID"),
        transaction_id=_text(node, "e:TransactionID"),
    )


def _findall(node: ET.Element, path: str) -> list[ET.Element]:
    return list(node.findall(path, NS))


def _text(node: ET.Element | None, path: str) -> str | None:
    if node is None:
        return None
    found = node.find(path, NS)
    if found is None or found.text is None:
        return None
    return found.text.strip()


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _first_error(root: ET.Element) -> str:
    parts = [
        _text(root, ".//e:ErrorCode"),
        _text(root, ".//e:ShortMessage"),
        _text(root, ".//e:LongMessage"),
    ]
    return " | ".join(part for part in parts if part) or "Keine Fehlermeldung im XML"
