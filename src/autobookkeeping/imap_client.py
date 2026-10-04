from __future__ import annotations

import email
import imaplib
import re
from datetime import date, timedelta
from email.message import Message
from html import unescape
from urllib.parse import unquote

from autobookkeeping.config import Settings
from autobookkeeping.models import DhlMailCandidate


LINK_RE = re.compile(r"https?://[^\s\"'<>)]+", re.IGNORECASE)
TRACKING_RE = re.compile(r"\b(?:[A-Z]{2}\d{9}[A-Z]{2}|\d{12,22})\b")


class GmxImapClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search_dhl_mails(self, days: int = 30, limit: int = 20) -> list[DhlMailCandidate]:
        if not self.settings.gmx_email or not self.settings.gmx_password:
            raise RuntimeError("GMX_EMAIL oder GMX_PASSWORD fehlt")

        since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
        with imaplib.IMAP4_SSL(self.settings.gmx_imap_host, self.settings.gmx_imap_port) as imap:
            try:
                imap.login(self.settings.gmx_email, self.settings.gmx_password)
            except imaplib.IMAP4.error as exc:
                raise RuntimeError(
                    "GMX IMAP Login fehlgeschlagen. Bitte in GMX POP3/IMAP aktivieren "
                    "und bei aktiver 2FA ein anwendungsspezifisches Passwort verwenden."
                ) from exc
            imap.select("INBOX")

            # GMX supports ordinary IMAP SEARCH. Keep it broad, then filter locally.
            status, data = imap.search(None, "SINCE", since, "TEXT", '"DHL"')
            if status != "OK":
                raise RuntimeError(f"IMAP search failed: {status}")
            uids = data[0].split()[-limit:]
            candidates = []
            for uid in reversed(uids):
                status, msg_data = imap.fetch(uid, "(RFC822)")
                if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                candidate = _parse_message(uid.decode(), msg)
                if "dhl" in (candidate.sender + " " + candidate.subject).lower() or candidate.links:
                    candidates.append(candidate)
            return candidates


def _parse_message(uid: str, msg: Message) -> DhlMailCandidate:
    body = _message_text(msg)
    links = _clean_links(LINK_RE.findall(body))
    tracking_numbers = sorted(set(TRACKING_RE.findall(body)))
    return DhlMailCandidate(
        uid=uid,
        subject=_decode_header(msg.get("Subject", "")),
        sender=_decode_header(msg.get("From", "")),
        date=msg.get("Date", ""),
        tracking_numbers=tracking_numbers,
        links=links,
    )


def _message_text(msg: Message) -> str:
    chunks: list[str] = []
    if msg.is_multipart():
        parts = msg.walk()
    else:
        parts = [msg]
    for part in parts:
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        chunks.append(payload.decode(charset, errors="replace"))
    return unescape("\n".join(chunks))


def _decode_header(value: str) -> str:
    parts = email.header.decode_header(value)
    decoded = []
    for text, charset in parts:
        if isinstance(text, bytes):
            decoded.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(text)
    return "".join(decoded)


def _clean_links(links: list[str]) -> list[str]:
    cleaned = []
    for link in links:
        value = unquote(link).rstrip(".,;")
        if value not in cleaned:
            cleaned.append(value)
    return cleaned
