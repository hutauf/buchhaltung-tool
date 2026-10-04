"""Resume publication without repeating bookkeeping, or update Bitcoin attestations."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "src"))
from autobookkeeping.workspace import data_root
ROOT = data_root()
from autobookkeeping.archive import verify_checkpoint
from autobookkeeping.publication import resume, Publication
from autobookkeeping.timestamps import verify_public, status
from autobookkeeping.local_invoices import WorkflowError


def confirm():
    with Publication(ROOT, "confirm Bitcoin timestamps", mode="proofs") as publication:
        results = []; changed = []
        for statement in sorted((ROOT / "buchhaltung/nachweise").glob("*.json")):
            proof = Path(str(statement) + ".ots"); before = proof.read_bytes()
            run = subprocess.run([sys.executable, str(TOOL / "scripts/ots_windows.py"), "upgrade", str(proof)],
                                 capture_output=True, timeout=60)
            if proof.read_bytes() != before: changed.append(proof.relative_to(ROOT).as_posix())
            entry = {"git_commit": statement.stem, "blockchain_verified": False, **status(statement, proof)}
            if entry["bitcoin_attestation_present"]:
                try:
                    verify_checkpoint(ROOT, statement); entry.update(verify_public(statement, proof))
                except Exception: entry["verification_pending"] = True
            if run.returncode: entry["upgrade_pending"] = True
            results.append(entry)
    return {"ok": True, "timestamps": results, "upgraded_proofs": len(changed), "publication": publication.result}


def main():
    parser = argparse.ArgumentParser(description="Buchhaltungs-Veröffentlichung und Bitcoin-Bestätigung")
    parser.add_argument("command", choices=("resume", "status", "confirm")); args = parser.parse_args()
    if args.command == "resume": result = resume(ROOT)
    elif args.command == "confirm": result = confirm()
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
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "hint": "Veröffentlichungsstatus prüfen und publish_bookkeeping.py resume verwenden; Buchung nicht wiederholen"})); sys.exit(1)
