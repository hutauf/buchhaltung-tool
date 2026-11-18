import io

import pytest
from bitcoin.core import coreparams
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation, VerificationError
from opentimestamps.core.op import OpSHA256
from opentimestamps.core.serialize import BytesSerializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile

from autobookkeeping.timestamps import EXPLORERS, load_proof, status, validate_headers


def responses():
    header = coreparams.GENESIS_BLOCK.get_header()
    return header, [{"source": base, "block_hash": header.GetHash()[::-1].hex(),
                     "header": header.serialize(), "tip_height": 10} for base in EXPLORERS]


def test_public_validation_checks_real_header_pow_and_ots_merkle_root():
    header, values = responses()
    result = validate_headers(header.hashMerkleRoot, BitcoinBlockHeaderAttestation(0), values)
    assert result["block_height"] == 0
    assert result["confirmations"] == 11
    assert result["sources"] == list(EXPLORERS)
    with pytest.raises(VerificationError):
        validate_headers(b"\x00" * 32, BitcoinBlockHeaderAttestation(0), values)


@pytest.mark.parametrize("failure", ["one_source", "duplicate_source", "different_hash", "different_header", "insufficient_confirmations", "false_hash"])
def test_public_validation_rejects_missing_or_conflicting_evidence(failure):
    header, values = responses()
    if failure == "one_source":
        values = values[:1]
    elif failure == "duplicate_source":
        values[1]["source"] = values[0]["source"]
    elif failure == "different_hash":
        values[1]["block_hash"] = "0" * 64
    elif failure == "different_header":
        values[1]["header"] = b"\0" * 80
    elif failure == "insufficient_confirmations":
        values[0]["tip_height"] = 4
    elif failure == "false_hash":
        for value in values:
            value["block_hash"] = "0" * 64
    with pytest.raises(ValueError):
        validate_headers(header.hashMerkleRoot, BitcoinBlockHeaderAttestation(0), values)


def test_proof_digest_binding_and_status_rereads_upgraded_file(tmp_path):
    data = b"git checkpoint data"
    statement = tmp_path / "statement.json"; statement.write_bytes(data)
    proof = tmp_path / "statement.json.ots"
    detached = DetachedTimestampFile.from_fd(OpSHA256(), io.BytesIO(data))
    detached.timestamp.attestations.add(PendingAttestation("https://alice.btc.calendar.opentimestamps.org"))
    def save():
        context = BytesSerializationContext()
        detached.serialize(context)
        proof.write_bytes(context.getbytes())
    save()
    assert not status(statement, proof)["bitcoin_attestation_present"]
    detached.timestamp.attestations.add(BitcoinBlockHeaderAttestation(42))
    save()
    assert status(statement, proof)["bitcoin_block_heights"] == [42]
    statement.write_bytes(b"changed Git checkpoint")
    with pytest.raises(ValueError):
        load_proof(statement, proof)


def cached_proof(tmp_path):
    from autobookkeeping.archive import sha
    statement = tmp_path / ('a' * 40 + '.json'); statement.write_bytes(b'{"synthetic":true}')
    proof = statement.with_suffix('.json.ots')
    detached = DetachedTimestampFile.from_fd(OpSHA256(), io.BytesIO(statement.read_bytes()))
    detached.timestamp.attestations.add(BitcoinBlockHeaderAttestation(0))
    context = BytesSerializationContext(); detached.serialize(context); proof.write_bytes(context.getbytes())
    entry = {'checked_at': '2011-01-01T00:00:00+00:00', 'statement_sha256': sha(statement.read_bytes()),
             'proof_sha256': sha(proof.read_bytes()), 'blockchain_verified': True,
             'verification_mode': 'public_explorers', 'block_height': 0, 'confirmations': 6}
    return statement, proof, entry


@pytest.mark.parametrize('changed', ['none', 'statement', 'proof', 'height', 'confirmations', 'mode', 'success', 'malformed', 'date'])
def test_cache_reuse_is_bound_to_exact_proof_and_successful_six_confirmation_check(tmp_path, changed):
    from autobookkeeping.timestamps import cache_matches
    statement, proof, entry = cached_proof(tmp_path)
    if changed == 'statement': statement.write_bytes(b'changed')
    elif changed == 'proof': proof.write_bytes(b'changed')
    elif changed == 'height': entry['block_height'] = 1
    elif changed == 'confirmations': entry['confirmations'] = 5
    elif changed == 'mode': entry['verification_mode'] = 'other'
    elif changed == 'success': entry['blockchain_verified'] = False
    elif changed == 'malformed': entry = None
    elif changed == 'date': entry['checked_at'] = '2011-01-01'
    assert cache_matches(entry, statement.read_bytes(), proof.read_bytes()) is (changed == 'none')


def test_staged_timestamp_summary_uses_two_git_processes_and_ignores_worktree(tmp_path, monkeypatch):
    import json
    import subprocess
    import autobookkeeping.timestamps as module
    subprocess.run(['git', 'init', str(tmp_path)], check=True, capture_output=True)
    root = tmp_path / 'buchhaltung/nachweise'; root.mkdir(parents=True)
    statement, proof, entry = cached_proof(root)
    (tmp_path / 'timestamp-status.json').write_text(json.dumps({'version': 1, 'entries': {statement.stem: entry}}))
    subprocess.run(['git', '-C', str(tmp_path), 'add', '.'], check=True, capture_output=True)
    # A second, missing proof is invalid; an unstaged successful cache must not count.
    missing = root / ('b' * 40 + '.json'); missing.write_bytes(b'{}')
    subprocess.run(['git', '-C', str(tmp_path), 'add', str(missing)], check=True, capture_output=True)
    statement.write_bytes(b'unstaged change'); proof.write_bytes(b'unstaged invalid proof')
    (tmp_path / 'timestamp-status.json').write_text('{}')
    calls = []; original = module.subprocess.run
    def counted(args, **kwargs):
        calls.append(args)
        return original(args, **kwargs)
    monkeypatch.setattr(module.subprocess, 'run', counted)
    assert module.dashboard_status(tmp_path, staged=True) == {
        'total': 2, 'verified': 1, 'pending': 0, 'unverified': 0, 'invalid': 1}
    assert len(calls) == 2
