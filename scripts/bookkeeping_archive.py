"""Local bookkeeping archive CLI. Errors never print source records or credentials."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from filelock import FileLock

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "src"))
from autobookkeeping.workspace import data_root
ROOT = TOOL / "daten"
from autobookkeeping.publication import Publication
from autobookkeeping.archive import Archive, atomic, cd_export, cd_verify, checkpoint, outside, unseal, verify_checkpoint


def arguments():
    parser = argparse.ArgumentParser(description="Verschlüsselte Buchhaltungsablage")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    p = sub.add_parser("import-local")
    p.add_argument("--metadata", type=Path, required=True)
    p.add_argument("--pdf", type=Path, action="append", required=True)
    p = sub.add_parser("evidence", help="Abrechnung/Zahlungsnachweis/Original archivieren; keine Ausgabe buchen")
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--metadata", type=Path, required=True)
    sub.add_parser("verify")
    p = sub.add_parser("report")
    p.add_argument("--year")
    p = sub.add_parser("retention", help="11-jährige Mindestaufbewahrung prüfen; keine Dateien löschen")
    p.add_argument("--as-of")
    p = sub.add_parser("export")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--year")
    p = sub.add_parser("decrypt")
    p.add_argument("document", help="Relativer .enc-Pfad unter buchhaltung")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("stamp")
    p.add_argument("--revision", default="HEAD")
    p = sub.add_parser("timestamps")
    p.add_argument("action", choices=["check", "upgrade", "verify", "info"])
    p.add_argument("--public", action="store_true", help="verify mit zwei öffentlichen Blockquellen statt eigenem Bitcoin-Core-Knoten")
    p = sub.add_parser("cd-export")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("cd-verify")
    p.add_argument("directory", type=Path)
    p = sub.add_parser("restore-bundle")
    p.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def run(args):
    archive = Archive(ROOT)
    if args.command == "init":
        archive.init()
        result = {"ok": True}
    elif args.command == "import-local":
        result = archive.import_local(args.metadata, args.pdf)
    elif args.command == "evidence":
        result = archive.import_evidence(args.file, args.metadata)
    elif args.command == "verify":
        result = archive.verify()

    elif args.command == "report":
        result = archive.report(args.year)
    elif args.command == "retention":
        from autobookkeeping.retention import report
        archive.verify()
        result = dict(report(archive.catalog(), args.as_of), ok=True)
    elif args.command == "export":
        result = archive.export(args.output, args.year)
    elif args.command == "decrypt":
        path = outside(ROOT, args.output)
        if path.exists():
            raise ValueError("Zieldatei existiert bereits")
        atomic(path, archive.read(args.document))
        result = {"ok": True, "output": str(path)}
    elif args.command == "stamp":
        archive.verify()
        path = checkpoint(ROOT, args.revision)
        proof = Path(str(path) + ".ots")
        if not proof.exists():
            subprocess.run([sys.executable, str(TOOL / "scripts/ots_windows.py"), "stamp", str(path)], check=True, timeout=60)
        result = {"ok": True, "statement": str(path), "proof": str(proof), "blockchain_verified": False}
    elif args.command == "timestamps":
        if args.public and args.action != "verify":
            raise ValueError("--public ist nur für timestamps verify vorgesehen")
        from autobookkeeping.timestamps import status, verify_public
        proofs = sorted((archive.root / "nachweise").glob("*.json"))
        if not proofs:
            raise ValueError("Keine Zeitnachweise vorhanden")
        result = []
        failed = False
        for path in proofs:
            entry = verify_checkpoint(ROOT, path)
            entry["blockchain_verified"] = False
            proof = Path(str(path) + ".ots")
            if not proof.exists():
                raise ValueError("OTS-Datei fehlt; stamp erneut ausführen")
            entry.update(status(path, proof))
            if args.action == "verify" and args.public:
                entry.update(verify_public(path, proof))
            elif args.action != "check":
                run = subprocess.run([sys.executable, str(TOOL / "scripts/ots_windows.py"), args.action, str(proof)], timeout=60)
                entry["ots_exit_code"] = run.returncode
                entry["blockchain_verified"] = args.action == "verify" and run.returncode == 0
                if args.action == "verify":
                    entry["verification_mode"] = "bitcoin_core"
                    entry["independent_full_node"] = run.returncode == 0
                # upgrade changes the proof, so return the new state rather than its old state.
                entry.update(status(path, proof))
                failed |= run.returncode != 0
            result.append(entry)
        return {"ok": not failed, "timestamps": result}
    elif args.command == "cd-export":
        from autobookkeeping.backups import export
        from autobookkeeping.local_invoices import LocalInvoices
        result = export(LocalInvoices(archive), args.output)
    elif args.command == "cd-verify":
        result = cd_verify(args.directory)
    elif args.command == "restore-bundle":
        path = outside(ROOT, args.output) / "repository.bundle"
        if path.exists():
            raise ValueError("Bundle-Ziel existiert bereits")
        atomic(path, unseal(archive.unlock(), (ROOT / "repository.bundle.enc").read_bytes(), "repository.bundle"))
        with tempfile.TemporaryDirectory(prefix="archive-bundle-verify-") as temporary:
            subprocess.run(["git", "init", "--quiet", temporary], check=True)
            subprocess.run(["git", "-C", temporary, "bundle", "verify", str(path)], check=True)
        result = {"ok": True, "bundle": str(path)}
    return result


def main() -> int:
    args = arguments()
    data_root()
    (ROOT / "output").mkdir(exist_ok=True)
    proof_write = args.command == "stamp" or args.command == "timestamps" and args.action == "upgrade"
    writes = proof_write or args.command in ("init", "import-local", "evidence", "cd-export")
    with Publication(ROOT, "archive " + args.command, enabled=writes, mode="proofs" if proof_write else "data") as publication:
        with FileLock(ROOT / "output/archive.lock", timeout=0):
            if (ROOT / "output/local-invoice-transaction.enc").exists():
                raise ValueError("Lokale Rechnungstransaktion zuerst mit local_invoice.py recover abschließen")
            result = run(args)
    if isinstance(result, dict):
        if writes: result["publication"] = publication.result
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(result.get("ok") is False)
    return result



if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Authentication failures and HTTP/API errors must not leak passwords/URLs.
        print(json.dumps({"ok": False, "error_type": type(exc).__name__,
                          "hint": "Passwort, Quelldaten, Pfade und Integrität prüfen; bei unterbrochener Veröffentlichung publish_bookkeeping.py status und resume verwenden"}))
        raise SystemExit(1)
