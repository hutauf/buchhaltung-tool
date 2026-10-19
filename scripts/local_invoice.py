"""Local trial / explicitly approved production workflow. All service calls read only."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "src"))

from autobookkeeping.workspace import data_root
from filelock import FileLock
from autobookkeeping.publication import Publication, resume
from autobookkeeping.archive import Archive, encoded, outside, sha
from autobookkeeping.handover import read_handover
from autobookkeeping.config import load_settings
from autobookkeeping.ebay_client import EbayTradingClient
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError
from autobookkeeping.adjustments import Adjustments, change_tax_profile
from autobookkeeping.cashflow import record_cash, void_cash
from autobookkeeping.vine_backend import VineBackendClient, candidate_matches, match_recommendation


def read_checks(order, settings) -> dict:
    checks = {}
    if bool(settings.vine_backend_url) != bool(settings.vine_backend_token):
        raise WorkflowError('Vine-Anbindung unvollständig: URL und Token gemeinsam konfigurieren oder beide weglassen')
    records = VineBackendClient(settings).get_all() if settings.vine_backend_url else []
    checks['vine_status'] = 'checked' if settings.vine_backend_url else 'not_configured'
    checks["vine"] = [{"item_index": index, "inventory": match_recommendation(records, item.title, 3),
                       "all_records_candidates": candidate_matches(records, item.title, item.price)[:3]}
                      for index, item in enumerate(order.items)]
    checks["vine_checked"] = bool(settings.vine_backend_url)
    # Use the existing IMAP helper; suppress signed receipt links in saved metadata/stdout.
    if order.tracking_number:
        run = subprocess.run([sys.executable, "-X", "utf8", str(TOOL / "scripts/find_dhl_receipt.py"), order.tracking_number],
                             cwd=data_root(), capture_output=True, timeout=90, check=True)
        result = json.loads(run.stdout)
        if not result.get("ok"):
            raise WorkflowError("DHL-Mailprüfung nicht erfolgreich")
        fields = ("uid", "date", "sender", "subject", "tracking_numbers", "prices_in_mail")
        checks["dhl"] = {"count": result["count"],
                         "mails": [{k: mail[k] for k in fields if k in mail} for mail in result["mails"]]}
    else:
        checks["dhl"] = {"count": 0, "note": "Kein Tracking; gezielte Mail-Suche erforderlich"}
    checks["dhl_checked"] = True
    return checks


def main() -> dict:
    parser = argparse.ArgumentParser(description="Lokale Rechnungen: zunächst unverbindliche Testentwürfe")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("configure", help="Lokales Absenderprofil und geprüften Nummernstand einrichten")
    p.add_argument("--profile", type=Path); p.add_argument('--interactive',action='store_true'); p.add_argument("--last-number", required=True)
    sub.add_parser("list")
    sub.add_parser("recover", help="Bereits autorisierte, unterbrochene Transaktion abschließen")
    p = sub.add_parser("prepare"); p.add_argument("order_id")
    p.add_argument("--receipt", type=Path); p.add_argument("--receipt-metadata", type=Path)
    p.add_argument("--vat-rates", nargs="+", type=int); p.add_argument("--replacement-of")
    p = sub.add_parser('manual-prepare', help='Manuelle Rechnung ohne eBay/DHL/Vine als unverbindlichen Entwurf erfassen')
    p.add_argument('--interactive', action='store_true'); p.add_argument('--metadata', type=Path)
    p.add_argument('--vat-rates', nargs='+',type=int); p.add_argument('--replacement-of')
    p = sub.add_parser("adjustment-prepare")
    p.add_argument("invoice_id"); p.add_argument("--kind", choices=("cancellation", "partial_refund", "correction"), required=True)
    p.add_argument("--metadata", type=Path); p.add_argument('--interactive',action='store_true')
    p = sub.add_parser("adjustment-issue")
    p.add_argument("id"); p.add_argument("--revision", required=True); p.add_argument("--number", required=True)
    p.add_argument("--approved", action="store_true")
    p = sub.add_parser("tax-profile")
    p.add_argument("--mode", choices=("small-business", "regular"), required=True)
    p.add_argument("--reason", required=True); p.add_argument("--approved", action="store_true")
    p = sub.add_parser("cash-record")
    p.add_argument("--metadata", type=Path); p.add_argument('--interactive',action='store_true'); p.add_argument('--record-id')
    p.add_argument("--approved", action="store_true")
    p = sub.add_parser("cash-void")
    p.add_argument("id"); p.add_argument("--reason", required=True); p.add_argument("--approved", action="store_true")
    p = sub.add_parser("preview"); p.add_argument("id"); p.add_argument("--output", required=True, type=Path)
    p.add_argument("--e-invoice", action="store_true", help="Validierte EN16931-XML zusätzlich exportieren; Testentwurf verbraucht keine Nummer")
    p = sub.add_parser("discard"); p.add_argument("id")
    p = sub.add_parser("activate", help="Lokale Nummernübergabe nach Freigabe aktivieren")
    p.add_argument("--last-number", required=True); p.add_argument("--handover", type=Path, required=True)
    p.add_argument("--approved", action="store_true")
    p = sub.add_parser("issue")
    p.add_argument("id"); p.add_argument("--revision", required=True); p.add_argument("--number", required=True)
    p.add_argument("--approved", action="store_true")
    p = sub.add_parser("expense")
    p.add_argument("invoice_id"); p.add_argument("--receipt-sha256", required=True); p.add_argument("--approved", action="store_true")
    args = parser.parse_args()
    ROOT = data_root()
    (ROOT / "output").mkdir(exist_ok=True)
    payload = None
    if args.command=='configure':
        if bool(args.profile)==bool(args.interactive): raise WorkflowError('Entweder --interactive oder --profile angeben')
        if args.interactive:
            from autobookkeeping import guided
            payload=guided.profile()
    if args.command in ('manual-prepare','adjustment-prepare','cash-record'):
        if bool(args.metadata) == bool(args.interactive): raise WorkflowError('Entweder --interactive oder --metadata angeben')
        if args.metadata: payload=json.loads(outside(ROOT,args.metadata).read_bytes())
        else:
            from autobookkeeping import guided
            if args.command=='manual-prepare': payload=guided.manual_invoice()
            elif args.command=='cash-record':
                if not args.record_id: raise WorkflowError('Beleg mit --record-id oder Dashboard-Aktion auswählen')
                payload=guided.payment(args.record_id);args.approved=True
            else:
                with FileLock(ROOT/'output/archive.lock',timeout=0):
                    a=Archive(ROOT);a.verify();catalog=a.catalog()
                payload=guided.adjustment(catalog,args.invoice_id,args.kind)
    if args.command == "recover" and (ROOT / "output/publication.json").exists():
        return {"ok": True, "publication": resume(ROOT)}
    with Publication(ROOT, "local invoice " + args.command, enabled=args.command in ['configure', 'prepare', 'manual-prepare', 'adjustment-prepare', 'adjustment-issue', 'tax-profile', 'cash-record', 'cash-void', 'discard', 'activate', 'issue', 'expense', 'recover']) as publication:
        with FileLock(ROOT / "output/archive.lock", timeout=0):
            archive = Archive(ROOT); workflow = LocalInvoices(archive)
            if args.command == "recover":
                result = {"ok": True, "recovered": workflow.recover()}
            else:
                if workflow.journal.exists():
                    raise WorkflowError("Unterbrochene Transaktion zuerst mit recover abschließen")
                archive.verify()
                if args.command == "configure":
                    profile = encoded(payload) if args.interactive else outside(ROOT, args.profile).read_bytes()
                    workflow.configure(json.loads(profile), args.last_number, {"source":"local_profile", "source_sha256":sha(profile)})
                    result = {"ok":True,"mode":"trial","profile_encrypted":True}
                elif args.command == "list":
                    catalog = archive.catalog()
                    result = {"mode": catalog.get("local_invoice_settings", {}).get("mode", "unconfigured"),
                              "drafts": [workflow.summary(v["current"], catalog) for v in catalog.get("local_invoice_drafts", {}).values()],
                              "adjustments": [Adjustments.summary(v["current"], catalog) for v in catalog.get("local_adjustment_drafts", {}).values()],
                              "cash_events": len(catalog.get("cash_events", {})),
                              "workflow": catalog.get("local_workflow", {})}
                elif args.command == "prepare":
                    if bool(args.receipt) != bool(args.receipt_metadata):
                        raise WorkflowError("Beleg-PDF und geprüfte Belegmetadaten gemeinsam angeben")
                    settings = load_settings(); order = EbayTradingClient(settings).get_order(args.order_id)
                    checks = read_checks(order, settings)
                    attachment = None
                    if args.receipt:
                        metadata = json.loads(outside(ROOT, args.receipt_metadata).read_bytes())
                        required = {"gross", "date", "vat_rate", "payee", "product", "cart_id", "verified", "verification_basis"}
                        if not required <= metadata.keys() or metadata.get("order_id") != order.order_id:
                            raise WorkflowError("Geprüfte Belegmetadaten mit genauem Bestellbezug erforderlich")
                        if metadata["verified"] is not True or metadata["vat_rate"] != 0:
                            raise WorkflowError("Nur einzeln geprüfte DHL-Originale mit 0 % Steuer vormerken")
                        attachment = (metadata, outside(ROOT, args.receipt).read_bytes())
                    result = workflow.prepare(order, checks, attachment, args.vat_rates, args.replacement_of)
                elif args.command == 'manual-prepare':
                    result=workflow.prepare_manual(payload,args.vat_rates,args.replacement_of)
                elif args.command == "adjustment-prepare":
                    result = Adjustments(workflow).prepare(args.invoice_id, args.kind, payload)
                elif args.command == "adjustment-issue":
                    result = Adjustments(workflow).issue(args.id, args.revision, args.number, args.approved)
                elif args.command == "tax-profile":
                    result = change_tax_profile(workflow, args.mode == "small-business", args.reason, args.approved)
                elif args.command == "cash-record":
                    result = record_cash(workflow, payload, args.approved)
                elif args.command == "cash-void":
                    result = void_cash(workflow, args.id, args.reason, args.approved)
                elif args.command == "preview":
                    result = workflow.preview(args.id, args.output, args.e_invoice)
                elif args.command == "discard":
                    result = workflow.discard(args.id)
                elif args.command == "activate":
                    if not args.approved:
                        raise WorkflowError("Produktivwechsel benötigt ausdrückliche Freigabe")
                    report, reference = read_handover(ROOT, args.handover)
                    result = workflow.activate(args.last_number, report["last_number"], args.approved, reference)
                elif args.command == "issue":
                    if not args.approved:
                        raise WorkflowError("Ausstellung benötigt ausdrückliche Freigabe")
                    invoice = archive.catalog()["local_invoice_drafts"][args.id]["current"]
                    order = None if invoice.get('entry_source')=='manual' else EbayTradingClient(load_settings()).get_order(invoice["order_id"])
                    result = workflow.issue(args.id, args.revision, args.number, order, args.approved)
                elif args.command == "expense":
                    result = workflow.expense(args.invoice_id, args.receipt_sha256, args.approved)
    if publication.enabled: result["publication"] = publication.result
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(), ensure_ascii=False, indent=2))
    except WorkflowError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    except Exception as exc:
        # HTTP responses may contain secrets or buyer details: never echo them.
        from autobookkeeping.diagnostics import failure
        print(json.dumps(failure(exc,TOOL/'daten'),ensure_ascii=False))
        raise SystemExit(1)
