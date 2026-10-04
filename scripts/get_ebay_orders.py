from __future__ import annotations

import argparse

from _agent_common import print_json
from autobookkeeping.config import load_settings
from autobookkeeping.ebay_client import EbayTradingClient
from autobookkeeping.workflow import summarize_order


def main() -> int:
    parser = argparse.ArgumentParser(description="Return recent eBay orders as JSON")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--fetch-limit", type=int, default=100)
    parser.add_argument("--paid-only", action="store_true", default=False)
    parser.add_argument("--shipped-only", action="store_true", default=False)
    args = parser.parse_args()

    orders = EbayTradingClient(load_settings()).get_orders(
        days=args.days,
        limit=max(args.limit, args.fetch_limit),
        shipped_only=args.shipped_only,
    )
    if args.paid_only:
        orders = [order for order in orders if order.paid_at is not None]
    orders = orders[: args.limit]

    print_json(
        {
            "ok": True,
            "count": len(orders),
            "orders": [summarize_order(order) for order in orders],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
