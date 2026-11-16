import imaplib
import ssl
from types import SimpleNamespace

import pytest

from autobookkeeping import imap_client
from autobookkeeping.diagnostics import failure


def settings():
    return SimpleNamespace(gmx_email='test@example.invalid', gmx_password='synthetic-secret',
                           gmx_imap_host='imap.example.invalid', gmx_imap_port=993)


def test_imap_verifies_tls_and_reads_without_marking_messages(monkeypatch):
    seen = {}
    class Mailbox:
        def __init__(self, host, port, *, ssl_context, timeout):
            assert ssl_context.check_hostname and ssl_context.verify_mode == ssl.CERT_REQUIRED
            assert timeout == 30
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, user, password): pass
        def select(self, mailbox, readonly):
            seen['readonly'] = readonly
            return 'OK', [b'1']
        def search(self, *args): return 'OK', [b'1']
        def fetch(self, uid, query):
            seen['fetch'] = query
            return 'OK', [(b'1', b'From: carrier@example.invalid\r\nSubject: DHL\r\n\r\nSynthetic receipt')]
    monkeypatch.setattr(imap_client.imaplib, 'IMAP4_SSL', Mailbox)
    assert len(imap_client.GmxImapClient(settings()).search_dhl_mails()) == 1
    assert seen == {'readonly': True, 'fetch': '(BODY.PEEK[])'}


def test_authentication_failure_is_distinct_and_never_contains_secret(monkeypatch):
    class Mailbox:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, *args): raise imaplib.IMAP4.error('synthetic-secret test@example.invalid')
    monkeypatch.setattr(imap_client.imaplib, 'IMAP4_SSL', Mailbox)
    with pytest.raises(imap_client.GmxAccessError) as caught:
        with imap_client.gmx_imap(settings()): pytest.fail('Login must fail')
    report = failure(caught.value)
    assert report['imap_stage'] == 'authentication'
    assert 'synthetic-secret' not in str(report) and 'test@example.invalid' not in str(report)


def test_certificate_failure_prevents_login(monkeypatch):
    def rejected(*args, **kwargs): raise ssl.SSLCertVerificationError('synthetic invalid certificate')
    monkeypatch.setattr(imap_client.imaplib, 'IMAP4_SSL', rejected)
    with pytest.raises(imap_client.GmxAccessError) as caught:
        with imap_client.gmx_imap(settings()): pytest.fail('TLS must fail before login')
    assert failure(caught.value)['imap_stage'] == 'tls_verification'


def test_failed_search_and_fetch_are_not_reported_as_missing_receipt():
    class Mailbox:
        def search(self, *args): return 'NO', [b'synthetic server failure']
        def fetch(self, *args): return 'NO', [b'synthetic server failure']
    with pytest.raises(imap_client.GmxAccessError) as search:
        imap_client.search_messages(Mailbox(), 'TEXT', 'synthetic')
    assert failure(search.value)['imap_stage'] == 'search'
    with pytest.raises(imap_client.GmxAccessError) as fetch:
        imap_client.read_message(Mailbox(), b'1')
    assert failure(fetch.value)['imap_stage'] == 'fetch'
