"""OTS proof validation with an explicit public-explorer trust model."""
from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
from bitcoin.core import CBlockHeader, CheckProofOfWork
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
from opentimestamps.core.op import OpSHA256
from opentimestamps.core.serialize import BytesDeserializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile

EXPLORERS = ("https://blockstream.info/api", "https://mempool.space/api")


def load_proof(statement: Path, proof: Path) -> DetachedTimestampFile:
    detached = DetachedTimestampFile.deserialize(BytesDeserializationContext(proof.read_bytes()))
    if not isinstance(detached.file_hash_op, OpSHA256) or detached.timestamp.msg != hashlib.sha256(statement.read_bytes()).digest():
        raise ValueError("OTS-Nachweis gehört nicht zur Git-Nachweisdatei")
    return detached


def status(statement: Path, proof: Path) -> dict:
    detached = load_proof(statement, proof)
    heights = sorted({a.height for _, a in detached.timestamp.all_attestations() if isinstance(a, BitcoinBlockHeaderAttestation)})
    return {"bitcoin_attestation_present": bool(heights), "bitcoin_block_heights": heights}


def explorer_header(base: str, height: int) -> dict:
    # Only public block heights/hashes are sent; the statement/proof stays local.
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        def text(path: str) -> str:
            response = client.get(base + path)
            response.raise_for_status()
            if len(response.content) > 1000:
                raise ValueError("Unerwartet große Blockantwort")
            return response.text.strip()
        block_hash = text(f"/block-height/{height}")
        if not re.fullmatch(r"[a-f0-9]{64}", block_hash):
            raise ValueError("Ungültiger Blockhash")
        header_hex = text(f"/block/{block_hash}/header")
        if not re.fullmatch(r"[a-fA-F0-9]{160}", header_hex):
            raise ValueError("Ungültiger Bitcoin-Blockheader")
        return {"source": base, "block_hash": block_hash, "header": bytes.fromhex(header_hex),
                "tip_height": int(text("/blocks/tip/height"))}


def validate_headers(message: bytes, attestation: BitcoinBlockHeaderAttestation, responses: list[dict]) -> dict:
    if len(responses) != len(EXPLORERS) or {r["source"] for r in responses} != set(EXPLORERS):
        raise ValueError("Zwei unterschiedliche vertrauenswürdige Blockquellen erforderlich")
    first = responses[0]
    if any(r["block_hash"] != first["block_hash"] or r["header"] != first["header"] for r in responses):
        raise ValueError("Blockchain-Quellen widersprechen sich")
    header = CBlockHeader.deserialize(first["header"])
    if header.GetHash()[::-1].hex() != first["block_hash"]:
        raise ValueError("Blockheader passt nicht zum Blockhash")
    CheckProofOfWork(header.GetHash(), header.nBits)
    # The official OTS implementation compares the derived proof digest with the Merkle root.
    timestamp = attestation.verify_against_blockheader(message, header)
    confirmations = min(r["tip_height"] - attestation.height + 1 for r in responses)
    if confirmations < 6:
        raise ValueError("Weniger als sechs Bitcoin-Bestätigungen")
    return {"block_height": attestation.height, "block_hash": first["block_hash"],
            "block_time_utc": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
            "confirmations": confirmations, "sources": list(EXPLORERS)}


def verify_public(statement: Path, proof: Path) -> dict:
    detached = load_proof(statement, proof)
    attestations = sorted([(m, a) for m, a in detached.timestamp.all_attestations()
                           if isinstance(a, BitcoinBlockHeaderAttestation)], key=lambda pair: pair[1].height)
    if not attestations:
        raise ValueError("Bitcoin-Bestätigung noch ausstehend; zuerst upgrade ausführen")
    failures = []
    for message, attestation in attestations:
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda base: explorer_header(base, attestation.height), EXPLORERS))
            result = validate_headers(message, attestation, responses)
            return {"blockchain_verified": True, "verification_mode": "public_explorers",
                    "independent_full_node": False, **result}
        except Exception as exc:
            failures.append(type(exc).__name__)
    raise ValueError("Keine Bitcoin-Attestierung über beide öffentlichen Quellen verifiziert: " + ", ".join(failures))
