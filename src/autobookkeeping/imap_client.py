from __future__ import annotations

import email
import imaplib
import re
import ssl
from contextlib import contextmanager
from datetime import date, timedelta
from email.message import Message
from html import unescape
from urllib.parse import unquote

import certifi

from autobookkeeping.config import Settings
from autobookkeeping.models import DhlMailCandidate


LINK_RE = re.compile(r"https?://[^\s\"'<>)]+", re.IGNORECASE)
TRACKING_RE = re.compile(r"\b(?:[A-Z]{2}\d{9}[A-Z]{2}|\d{12,22})\b")


class GmxAccessError(imaplib.IMAP4.error):
    """A safe failure stage; never retain a server response or credentials."""
    def __init__(self, stage):
        self.stage = stage
        super().__init__('GMX IMAP access failed')


@contextmanager
def gmx_imap(settings):
    if not settings.gmx_email or not settings.gmx_password:
        raise GmxAccessError('configuration')
    # IMAP4_SSL without an explicit context does not verify the server certificate.
    # Keep hostname verification enabled and use the maintained Mozilla trust roots.
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        connection = imaplib.IMAP4_SSL(settings.gmx_imap_host, settings.gmx_imap_port,
                                      ssl_context=context, timeout=30)
    except ssl.SSLCertVerificationError:
        raise GmxAccessError('tls_verification') from None
    except (OSError, imaplib.IMAP4.error):
        raise GmxAccessError('connection') from None
    with connection as imap:
        try:
            imap.login(settings.gmx_email, settings.gmx_password)
        except imaplib.IMAP4.error:
            raise GmxAccessError('authentication') from None
        try:
            status, _ = imap.select('INBOX', readonly=True)
        except imaplib.IMAP4.error:
            raise GmxAccessError('mailbox') from None
        if status != 'OK':
            raise GmxAccessError('mailbox')
        yield imap


def search_messages(imap, *criteria):
    try:
        status, data = imap.search(None, *criteria)
    except imaplib.IMAP4.error:
        raise GmxAccessError('search') from None
    if status != 'OK':
        raise GmxAccessError('search')
    return data[0].split() if data and data[0] else []


def read_message(imap, message_id):
    try:
        status, data = imap.fetch(message_id, '(BODY.PEEK[])')
    except imaplib.IMAP4.error:
        raise GmxAccessError('fetch') from None
    parts = [part[1] for part in (data or []) if isinstance(part, tuple) and isinstance(part[1], bytes)]
    if status != 'OK' or len(parts) != 1:
        raise GmxAccessError('fetch')
    return email.message_from_bytes(parts[0])


class GmxImapClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search_dhl_mails(self, days: int = 30, limit: int = 20) -> list[DhlMailCandidate]:
        if not self.settings.gmx_email or not self.settings.gmx_password:
            raise RuntimeError("GMX_EMAIL oder GMX_PASSWORD fehlt")

        since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
        with gmx_imap(self.settings) as imap:

            # GMX supports ordinary IMAP SEARCH. Keep it broad, then filter locally.
            uids = search_messages(imap, 'SINCE', since, 'TEXT', '"DHL"')[-limit:]
            candidates = []
            for uid in reversed(uids):
                msg = read_message(imap, uid)
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
