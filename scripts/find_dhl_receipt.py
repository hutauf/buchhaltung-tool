from __future__ import annotations

import argparse
import re
from pathlib import Path

from _agent_common import print_json, ROOT
from autobookkeeping.config import load_settings
from autobookkeeping.dhl_receipts import download_receipt_from_link, likely_invoice_links
from autobookkeeping.imap_client import _message_text, _parse_message, gmx_imap, search_messages, read_message


def main() -> int:
    parser = argparse.ArgumentParser(description="Find DHL mail by tracking number and optionally download receipt")
    parser.add_argument("tracking_number")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "downloads/dhl")
    args = parser.parse_args()

    settings = load_settings()
    mails = []
    with gmx_imap(settings) as imap:
        ids = search_messages(imap, 'TEXT', f'"{args.tracking_number}"')
        for uid in ids:
            msg = read_message(imap, uid)
            candidate = _parse_message(uid.decode(), msg)
            body = _message_text(msg)
            invoice_links = [
                link for link in likely_invoice_links(candidate.links) if "restweb/Invoice" in link
            ]
            mail = {
                "uid": candidate.uid,
                "date": candidate.date,
                "sender": candidate.sender,
                "subject": candidate.subject,
                "tracking_numbers": candidate.tracking_numbers,
                "invoice_links": invoice_links,
                "prices_in_mail": sorted(set(re.findall(r"\d+,\d{2}\s*€", body))),
            }
            if args.download and invoice_links:
                path = download_receipt_from_link(invoice_links[0], args.output_dir)
                mail["downloaded_receipt"] = {"path": str(path), "bytes": path.stat().st_size}
            mails.append(mail)

    print_json({"ok": True, "tracking_number": args.tracking_number, "count": len(mails), "mails": mails})
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        from autobookkeeping.diagnostics import failure
        print_json(failure(exc));raise SystemExit(1)
