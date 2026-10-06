"""Resolve opaque dashboard refs locally; never expose private identifiers in HTML."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "src"))
from autobookkeeping.workspace import data_root
ROOT = TOOL / 'daten'
from filelock import FileLock
from autobookkeeping.archive import Archive, atomic, encoded, outside, sha
from autobookkeeping.local_invoices import WorkflowError


def resolve(catalog, reference):
    if not re.fullmatch(r"[a-f0-9]{20}", reference): raise WorkflowError("Ungültige Dashboard-Referenz")
    rows = [(section, v["current"]) for section in ("records", "local_invoice_drafts", "local_adjustment_drafts", "local_expense_drafts")
            for v in catalog.get(section, {}).values() if sha(v["current"]["id"].encode())[:20] == reference]
    if len(rows) != 1: raise WorkflowError("Dashboard-Referenz fehlt oder ist nicht eindeutig")
    return rows[0]


def command(args, section, row):
    rid = row["id"]
    if args.action == "preview":
        if not args.output: raise WorkflowError("Neuen Ausgabeordner außerhalb des Repos angeben")
        if row.get("kind", "invoice") == "expense":
            return ["receipt.py", "inspect", str(ROOT / "buchhaltung" / row["documents"][0]), "--output", str(args.output)]
        return ["local_invoice.py", "preview", rid, "--output", str(args.output), *(['--e-invoice'] if getattr(args,'e_invoice',False) else [])]
    if args.action == "finish":
        if section not in ("local_invoice_drafts", "local_adjustment_drafts", "local_expense_drafts"):
            raise WorkflowError("Kein lokaler Entwurf")
        if row["status"] != "test_draft": raise WorkflowError("Nur ungebuchte Entwürfe abschließen")
        if section == "local_expense_drafts":
            return ["receipt.py", "book", rid, "--revision", row["revision"], "--approved"]
        if not args.number: raise WorkflowError("Vorgeschlagene konkrete Rechnungs-/Korrekturnummer erforderlich")
        sub = "adjustment-issue" if section == "local_adjustment_drafts" else "issue"
        return ["local_invoice.py", sub, rid, "--revision", row["revision"], "--number", args.number, "--approved"]
    if args.action == "discard":
        if section not in ("local_invoice_drafts", "local_adjustment_drafts", "local_expense_drafts"):
            raise WorkflowError("Kein lokaler Entwurf")
        if row["status"] != "test_draft": raise WorkflowError("Nur aktive Entwürfe verwerfen")
        return ["receipt.py" if section == "local_expense_drafts" else "local_invoice.py", "discard", rid]
    if args.action == "dhl-expense":
        if row.get("source") != "local" or row.get("kind") != "invoice": raise WorkflowError("Lokale ausgestellte Rechnung erforderlich")
        value = next((v["current"] for v in args.catalog.get("local_invoice_drafts", {}).values()
                      if v["current"].get("invoice_id") == rid), None)
        if not value or not value.get("receipt_candidate"): raise WorkflowError("Kein verifizierter DHL-Beleg vorgemerkt")
        return ["local_invoice.py", "expense", rid, "--receipt-sha256", sha(encoded(value["receipt_candidate"])), "--approved"]
    if args.action in ("cancel-prepare", "refund-prepare", "correct-prepare"):
        if row["kind"] != "invoice" or section != "records": raise WorkflowError("Ausgestellte Originalrechnung erforderlich")
        if not args.metadata: raise WorkflowError("Geprüfte Korrekturmetadaten außerhalb des Repos angeben")
        kind = {"cancel-prepare": "cancellation", "refund-prepare": "partial_refund", "correct-prepare": "correction"}[args.action]
        return ["local_invoice.py", "adjustment-prepare", rid, "--kind", kind, "--metadata", str(args.metadata)]
    raise WorkflowError("Aktion nicht unterstützt")


def main():
    data_root()
    parser = argparse.ArgumentParser(description="Lokale Aktion aus einem geprüften Dashboard-Stand")
    parser.add_argument("action", choices=("show", "preview", "finish", "discard", "dhl-expense", "cancel-prepare", "refund-prepare", "correct-prepare", "payments"))
    parser.add_argument("--ref", required=True); parser.add_argument("--snapshot", required=True)
    parser.add_argument("--number"); parser.add_argument("--metadata", type=Path); parser.add_argument("--output", type=Path)
    parser.add_argument("--e-invoice", action="store_true", help="Archivierte Rechnungs-XML zusätzlich ansehen")
    parser.add_argument("--approved", action="store_true"); args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{64}", args.snapshot): raise WorkflowError("Ungültiger Dashboard-Snapshot")
    with FileLock(ROOT / "output/archive.lock", timeout=0):
        archive = Archive(ROOT); archive.verify()
        if sha((archive.root / "database.json.enc").read_bytes()) != args.snapshot: raise WorkflowError("Dashboard veraltet; neu erzeugen und aktuellen Befehl verwenden")
        catalog = archive.catalog(); section, row = resolve(catalog, args.ref); args.catalog = catalog
    if args.action == "show":
        print(json.dumps({"ok": True, "record": row}, ensure_ascii=False, indent=2)); return 0
    if args.action == "preview" and section == "records" and row["kind"] != "expense":
        if not args.output: raise WorkflowError("Neuen Ausgabeordner außerhalb des Repos angeben")
        target = outside(ROOT, args.output)
        if target.exists(): raise WorkflowError("Vorschauziel muss neu sein")
        if not row.get("documents"): raise WorkflowError("Kein Original im Archiv vorhanden")
        atomic(target / "original.pdf", archive.read(row["documents"][0]))
        if args.e_invoice:
            for name in row['documents']:
                if name.endswith('.xml.enc') or name.endswith('.validation.json.enc'):
                    atomic(target / Path(name[:-4]).name,archive.read(name))
        atomic(target / "metadaten.json", encoded(row))
        print(json.dumps({"ok": True, "output": str(target)}, ensure_ascii=False)); return 0
    if args.action in ("finish", "payments", "dhl-expense") and not args.approved:
        raise WorkflowError("Konkreter Abschluss/Zahlung benötigt --approved")
    environment = dict(os.environ, BOOKKEEPING_EXPECTED_SNAPSHOT=args.snapshot)
    if args.action == "payments":
        if not args.metadata: raise WorkflowError("Geprüfte Zahlungsmetadaten außerhalb des Repos angeben")
        payload = json.loads(outside(ROOT, args.metadata).read_bytes())
        if payload.get("record_id", row["id"]) != row["id"]: raise WorkflowError("Zahlung gehört zu einem anderen Beleg")
        payload["record_id"] = row["id"]
        with tempfile.TemporaryDirectory(prefix="bookkeeping-payment-") as temp:
            path = Path(temp) / "payment.json"; path.write_bytes(encoded(payload))
            return subprocess.call([sys.executable, "-X", "utf8", str(TOOL / "scripts/local_invoice.py"), "cash-record", "--metadata", str(path), "--approved"], cwd=ROOT, env=environment)
    argv = command(args, section, row)
    return subprocess.call([sys.executable, "-X", "utf8", str(TOOL / "scripts" / argv[0]), *argv[1:]], cwd=ROOT, env=environment)


if __name__ == "__main__":
    try: raise SystemExit(main())
    except WorkflowError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)); sys.exit(1)
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__})); sys.exit(1)
