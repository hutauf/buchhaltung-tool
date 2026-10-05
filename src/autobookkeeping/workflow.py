"""Read-only eBay order summaries for local bookkeeping."""
from typing import Any
from autobookkeeping.models import EbayOrder


def summarize_order(order: EbayOrder) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "order_id_aliases": list(order.order_id_aliases),
        "sales_record_number": order.sales_record_number,
        "order_status": order.order_status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "buyer_username": order.buyer_username,
        "customer": order.shipping_address.name,
        "city": order.shipping_address.city,
        "total_value": order.total_value,
        "item_total": order.item_total,
        "shipping_cost": order.shipping_cost,
        "currency": order.currency,
        "tracking_number": order.tracking_number,
        "tracking_carrier": order.tracking_carrier,
        "items": [
            {
                "title": item.title,
                "quantity": item.quantity,
                "price": item.price,
                "currency": item.currency,
            }
            for item in order.items
        ],
    }
