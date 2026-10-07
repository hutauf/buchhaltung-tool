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


def dashboard_status(repo: Path, staged=False) -> dict:
    """Cached verification counts, bound to exact proof and statement bytes."""
    import json
    import subprocess
    from autobookkeeping.workspace import git_environment
    from autobookkeeping.archive import sha
    def read(name):
        if staged:
            try: return subprocess.check_output(['git','-C',str(repo),'show',':'+name],env=git_environment(),stderr=subprocess.PIPE)
            except subprocess.CalledProcessError: return None
        path=repo/name
        return path.read_bytes() if path.is_file() else None
    cache=json.loads(read('timestamp-status.json') or b'{"entries":{}}')
    names=subprocess.check_output(['git','-C',str(repo),'ls-files','-z','--','buchhaltung/nachweise'],env=git_environment()).decode().split('\0') if staged else [p.relative_to(repo).as_posix() for p in (repo/'buchhaltung/nachweise').glob('*.json')]
    result={'total':0,'verified':0,'pending':0,'unverified':0,'invalid':0}
    for name in names:
        if not re.fullmatch(r'buchhaltung/nachweise/[a-f0-9]{40}(?:[a-f0-9]{24})?\.json',name): continue
        result['total']+=1; raw=read(name); proof=read(name+'.ots')
        try:
            detached=DetachedTimestampFile.deserialize(BytesDeserializationContext(proof))
            if not isinstance(detached.file_hash_op,OpSHA256) or detached.timestamp.msg!=hashlib.sha256(raw).digest():
                raise ValueError('Proof mismatch')
            entry=cache.get('entries',{}).get(Path(name).stem,{})
            heights={a.height for _,a in detached.timestamp.all_attestations() if isinstance(a,BitcoinBlockHeaderAttestation)}
            if (entry.get('blockchain_verified') is True and entry.get('statement_sha256')==sha(raw)
                and entry.get('proof_sha256')==sha(proof) and entry.get('block_height') in heights
                and entry.get('verification_mode')=='public_explorers'
                and type(entry.get('confirmations')) is int and entry['confirmations']>=6):
                result['verified']+=1
            elif heights: result['unverified']+=1
            else: result['pending']+=1
        except Exception: result['invalid']+=1
    return result
