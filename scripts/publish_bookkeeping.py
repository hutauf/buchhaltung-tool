"""Resume publication without repeating bookkeeping, or update Bitcoin attestations."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "src"))
from autobookkeeping.workspace import data_root
ROOT = TOOL / "daten"
from autobookkeeping.archive import verify_checkpoint, atomic, encoded, sha
from autobookkeeping.local_invoices import now
from autobookkeeping.publication import resume, Publication
from autobookkeeping.timestamps import cache_matches, verify_public, status
from autobookkeeping.local_invoices import WorkflowError


def confirm(full=False):
    with Publication(ROOT, "confirm Bitcoin timestamps", mode="proofs") as publication:
        cache_path = ROOT / 'timestamp-status.json'
        previous = json.loads(cache_path.read_bytes()) if cache_path.exists() else {'version': 1, 'entries': {}}
        results = []; changed = []; cache={'version':1,'entries':{}}
        reused = 0; checked = 0
        for statement in sorted((ROOT / "buchhaltung/nachweise").glob("*.json")):
            proof = Path(str(statement) + ".ots"); before = proof.read_bytes()
            old = previous.get('entries', {}).get(statement.stem, {}) if previous.get('version') == 1 else {}
            if not full and cache_matches(old, statement.read_bytes(), before):
                # Keep the date and confirmations of the actual historical check.
                # Reuse must not pretend that a new network/Git check took place.
                cache['entries'][statement.stem] = old
                results.append({'git_commit': statement.stem, **old, 'reused': True})
                reused += 1
                continue
            checked += 1
            try:
                run = subprocess.run([sys.executable, str(TOOL / "scripts/ots_windows.py"), "upgrade", str(proof)],
                                     capture_output=True, timeout=60)
                upgrade_pending = bool(run.returncode)
            except subprocess.TimeoutExpired:
                upgrade_pending = True
            if proof.read_bytes() != before: changed.append(proof.relative_to(ROOT).as_posix())
            entry = {"git_commit": statement.stem, "blockchain_verified": False, **status(statement, proof)}
            if entry["bitcoin_attestation_present"]:
                try:
                    verify_checkpoint(ROOT, statement); entry.update(verify_public(statement, proof))
                except Exception: entry["verification_pending"] = True
            if upgrade_pending: entry["upgrade_pending"] = True
            cache['entries'][statement.stem] = {
                'checked_at':now(), 'statement_sha256':sha(statement.read_bytes()),'proof_sha256':sha(proof.read_bytes()),
                'blockchain_verified':entry['blockchain_verified'],
                'verification_mode':entry.get('verification_mode'), 'block_height':entry.get('block_height'),
                'block_time_utc':entry.get('block_time_utc'), 'confirmations':entry.get('confirmations')}
            results.append(entry)
        if cache != previous:
            atomic(cache_path, encoded(cache))
    return {"ok": True, "timestamps": results, "checked_proofs": checked, "reused_proofs": reused,
            "full_check": full, "upgraded_proofs": len(changed), "publication": publication.result}


def main():
    parser = argparse.ArgumentParser(description="Buchhaltungs-Veröffentlichung und Bitcoin-Bestätigung")
    parser.add_argument("command", choices=("resume", "status", "confirm"))
    parser.add_argument('--full', action='store_true', help='Alle Bitcoin-/Git-Nachweise erneut prüfen, auch bereits bestätigte')
    args = parser.parse_args()
    if args.full and args.command != 'confirm':
        parser.error('--full ist nur für confirm vorgesehen')
    data_root()
    if args.command == "resume": result = resume(ROOT)
    elif args.command == "confirm": result = confirm(full=args.full)
    else:
        path = ROOT / "output/publication.json"
        result = {"pending": path.exists(), "resume_command": ".venv\\Scripts\\python.exe -X utf8 scripts\\publish_bookkeeping.py resume"}
        configuration=json.loads((ROOT/'workspace.json').read_bytes()) if (ROOT/'workspace.json').exists() else {}
        result['setup_pending']=not bool(configuration.get('expected_push_url'))
        if result['setup_pending']:result['next']='Privates GitHub-Ziel einrichten und Migration mit Push und Zeitnachweis abschließen; neue Buchungen sind gesperrt'
        if path.exists():
            value = json.loads(path.read_bytes()); result.update({k:value[k] for k in ("action", "phase", "data_commit", "proof_commit") if k in value})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try: main()
    except WorkflowError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)); sys.exit(1)
    except Exception as exc:
        from autobookkeeping.diagnostics import failure
        print(json.dumps(failure(exc,ROOT),ensure_ascii=False)); sys.exit(1)
