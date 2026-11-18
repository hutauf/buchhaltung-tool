"""Network-independent confirmation scheduling and exact-byte cache invalidation."""
import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_timestamps import cached_proof

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def confirmation(tmp_path, monkeypatch):
    script = runpy.run_path(str(ROOT/'scripts/publish_bookkeeping.py'))
    namespace = script['confirm'].__globals__
    proofs = tmp_path/'buchhaltung/nachweise'; proofs.mkdir(parents=True)
    statement, proof, entry = cached_proof(proofs)
    cache = {'version': 1, 'entries': {statement.stem: entry}}
    cache_path = tmp_path/'timestamp-status.json'
    cache_path.write_text(json.dumps(cache), encoding='utf8')
    class Publication:
        def __init__(self, *args, **kwargs):
            self.result = {'status': 'synthetic'}
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setitem(namespace, 'ROOT', tmp_path)
    monkeypatch.setitem(namespace, 'Publication', Publication)
    return namespace, statement, proof, entry, cache_path


def test_confirm_reuses_complete_unchanged_verification_without_network_or_cache_write(confirmation, monkeypatch):
    namespace, statement, proof, entry, cache_path = confirmation
    before = cache_path.read_bytes(); modified = cache_path.stat().st_mtime_ns
    def forbidden(*args, **kwargs):
        pytest.fail('An unchanged confirmed proof requires no network or historical Git replay')
    monkeypatch.setattr(namespace['subprocess'], 'run', forbidden)
    monkeypatch.setitem(namespace, 'verify_checkpoint', forbidden)
    monkeypatch.setitem(namespace, 'verify_public', forbidden)
    result = namespace['confirm']()
    assert result['reused_proofs'] == 1 and result['checked_proofs'] == 0
    assert result['timestamps'][0]['checked_at'] == entry['checked_at']
    assert result['timestamps'][0]['reused'] is True
    assert cache_path.read_bytes() == before and cache_path.stat().st_mtime_ns == modified


@pytest.mark.parametrize('reason', ['full', 'unverified', 'changed_proof'])
def test_confirmation_rechecks_full_request_or_invalidated_cache(confirmation, monkeypatch, reason):
    namespace, statement, proof, entry, cache_path = confirmation
    if reason == 'unverified':
        entry['blockchain_verified'] = False
        cache_path.write_text(json.dumps({'version': 1, 'entries': {statement.stem: entry}}))
    elif reason == 'changed_proof':
        from opentimestamps.core.notary import PendingAttestation
        from opentimestamps.core.serialize import BytesSerializationContext
        from autobookkeeping.timestamps import load_proof
        detached = load_proof(statement, proof)
        detached.timestamp.attestations.add(PendingAttestation('https://calendar.example.invalid'))
        context = BytesSerializationContext(); detached.serialize(context); proof.write_bytes(context.getbytes())
    calls = []
    monkeypatch.setattr(namespace['subprocess'], 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setitem(namespace, 'verify_checkpoint', lambda *args: calls.append('git'))
    monkeypatch.setitem(namespace, 'verify_public', lambda *args: (calls.append('bitcoin') or {
        'blockchain_verified': True, 'block_height': 0, 'confirmations': 10,
        'verification_mode': 'public_explorers', 'block_time_utc': '2011-01-01T00:00:00+00:00'}))
    result = namespace['confirm'](full=reason == 'full')
    assert calls == ['git', 'bitcoin']
    assert result['checked_proofs'] == 1 and result['reused_proofs'] == 0
    updated = json.loads(cache_path.read_bytes())['entries'][statement.stem]
    assert updated['blockchain_verified'] is True and updated['confirmations'] == 10


def test_confirmation_timeout_stays_pending_instead_of_claiming_success(confirmation, monkeypatch):
    namespace, statement, proof, entry, cache_path = confirmation
    cache_path.write_text('{"version":1,"entries":{}}')
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('synthetic upgrade', 60)
    monkeypatch.setattr(namespace['subprocess'], 'run', timeout)
    monkeypatch.setitem(namespace, 'verify_checkpoint', lambda *args: None)
    monkeypatch.setitem(namespace, 'verify_public', lambda *args: (_ for _ in ()).throw(OSError('offline')))
    result = namespace['confirm']()
    assert result['timestamps'][0]['upgrade_pending'] is True
    assert result['timestamps'][0]['verification_pending'] is True
    assert json.loads(cache_path.read_bytes())['entries'][statement.stem]['blockchain_verified'] is False
