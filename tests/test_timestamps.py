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
