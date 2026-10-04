"""Homeoffice-Tagespauschale: Vorschau oder freigegebener Jahresstand."""
import argparse
import json
import os
import re
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "src"))
from autobookkeeping.workspace import data_root
ROOT = data_root()
from filelock import FileLock
from autobookkeeping.archive import Archive
from autobookkeeping.homeoffice import calculate, record, public_allowances, eur_summary, DEFAULT_DAYS
from autobookkeeping.publication import Publication
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError


def main():
    parser = argparse.ArgumentParser(description="6 EUR je berechtigtem Homeoffice-Tag, Jahreslimit 1260 EUR")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "set"):
        p = sub.add_parser(command)
        p.add_argument("--year", type=int, required=True); p.add_argument("--days", type=int, default=DEFAULT_DAYS)
        p.add_argument("--other-claimed", default="0.00", help="Im selben Jahr bei anderen Tätigkeiten beanspruchte Tagespauschale in EUR")
        if command == "set":
            p.add_argument("--basis", required=True, help="Tagesaufstellung/Nachweis, Berechtigung und keine Doppelzuordnung")
            p.add_argument("--eligible", action="store_true", help="Berechtigte, dieser EÜR zugeordnete Tage; keine ausschließenden Arbeitszimmer-/Unterkunftsabzüge für diese Tage")
            p.add_argument("--approved", action="store_true")
            p.add_argument("--snapshot", help="Veraltete Dashboard-Befehle blockieren")
    sub.add_parser("list")
    p = sub.add_parser("report"); p.add_argument("--year", type=int)
    args = parser.parse_args()
    if getattr(args, "snapshot", None):
        if not re.fullmatch(r"[a-f0-9]{64}", args.snapshot): raise WorkflowError("Ungültiger Dashboard-Snapshot")
        os.environ["BOOKKEEPING_EXPECTED_SNAPSHOT"] = args.snapshot
    if args.command == "preview":
        result = {"ok": True, "saved": False, **calculate(args.year, args.days, args.other_claimed)}
    else:
        (ROOT / "output").mkdir(exist_ok=True)
        with Publication(ROOT, "homeoffice " + args.command, enabled=args.command in ['set']) as publication:
            with FileLock(ROOT / "output/archive.lock", timeout=0):
                workflow = LocalInvoices(Archive(ROOT))
                if workflow.journal.exists(): raise WorkflowError("Offene Archivtransaktion zuerst mit local_invoice.py recover abschließen")
                if args.command == "set": result = record(workflow, args.year, args.days, args.basis, args.eligible, args.approved, args.other_claimed)
                else:
                    workflow.archive.verify(); catalog = workflow.archive.catalog()
                    result = {"ok": True, "homeoffice": public_allowances(catalog)} if args.command == "list" else {"ok": True, **eur_summary(catalog, args.year)}
        if publication.enabled: result["publication"] = publication.result
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try: main()
    except WorkflowError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)); sys.exit(1)
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "hint": "publish_bookkeeping.py status und resume verwenden; gespeicherte Buchung nicht wiederholen"})); sys.exit(1)
