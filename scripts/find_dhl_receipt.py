from __future__ import annotations

import argparse
import email
import imaplib
import re
from pathlib import Path

from _agent_common import print_json, ROOT
from autobookkeeping.config import load_settings
from autobookkeeping.dhl_receipts import download_receipt_from_link, likely_invoice_links
from autobookkeeping.imap_client import _message_text, _parse_message


def main() -> int:
    parser = argparse.ArgumentParser(description="Find DHL mail by tracking number and optionally download receipt")
    parser.add_argument("tracking_number")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "downloads/dhl")
    args = parser.parse_args()

    settings = load_settings()
    mails = []
    with imaplib.IMAP4_SSL(settings.gmx_imap_host, settings.gmx_imap_port) as imap:
        imap.login(settings.gmx_email, settings.gmx_password)
        imap.select("INBOX")
        status, data = imap.search(None, "TEXT", f'"{args.tracking_number}"')
        ids = data[0].split() if status == "OK" and data else []
        for uid in ids:
            status, msg_data = imap.fetch(uid, "(RFC822)")
            if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                continue
            msg = email.message_from_bytes(msg_data[0][1])
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
    raise SystemExit(main())
