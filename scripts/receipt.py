"""All-purpose expense receipts: inspect -> prepare -> approve -> book."""
from __future__ import annotations
import argparse
import json
import os
import sys
import uuid
from pathlib import Path
TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOL/"src"))
from autobookkeeping.workspace import data_root
ROOT = TOOL / "daten"
from filelock import FileLock
from autobookkeeping.publication import Publication
from autobookkeeping.archive import Archive
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError
from autobookkeeping.receipts import Receipts


def main():
    parser=argparse.ArgumentParser(description="Beliebige Ausgabenbelege lokal prüfen und nach Freigabe verschlüsselt buchen")
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("inspect",help="PDF/XML/Bild lokal lesen; XML validieren und Metadaten außerhalb vorbefüllen")
    p.add_argument("path",type=Path);p.add_argument("--output",type=Path)
    p.add_argument('--original-id',help='Vorhandene Originalausgabe für Lieferanten-Storno/Minderung')
    p=sub.add_parser('neu',help='Original lesen und Metadaten im Terminal erfassen; nur Entwurf, keine Ausgabenbuchung')
    p.add_argument('path',type=Path);p.add_argument('--output',type=Path);p.add_argument('--original-id')
    p=sub.add_parser("prepare",help="Geprüfte Metadaten verschlüsselt vormerken; noch keine Ausgabe buchen")
    p.add_argument("review",type=Path);p.add_argument("--metadata",type=Path);p.add_argument('--interactive',action='store_true')
    sub.add_parser("list",help="Ungebuchte Belegvormerkungen anzeigen")
    p=sub.add_parser("show");p.add_argument("id")
    p=sub.add_parser("book",help="Genau die freigegebene Metadatenrevision als Ausgabe buchen")
    p.add_argument("id");p.add_argument("--revision",required=True);p.add_argument("--approved",action="store_true")
    p=sub.add_parser("discard");p.add_argument("id")
    p=sub.add_parser('invalidieren',help='Fehlerhafte erfasste Ausgaben nachvollziehbar ausschließen; keine Löschung oder Rückzahlung')
    p.add_argument('ids',nargs='+');p.add_argument('--reason');p.add_argument('--interactive',action='store_true')
    p.add_argument('--approved',action='store_true')
    args=parser.parse_args();data_root();(ROOT/"output").mkdir(exist_ok=True)
    if args.command=='neu':
        base=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'.cache')/'BuchhaltungTool'/'belegpruefung'
        with FileLock(ROOT/'output/archive.lock',timeout=0):
            result=Receipts(LocalInvoices(Archive(ROOT))).inspect(args.path,args.output or base/uuid.uuid4().hex,args.original_id)
        print('Original und Prüfkopien:',Path(result['review']).parent)
        args.command='prepare';args.review=Path(result['review']);args.metadata=Path(result['metadata']);args.interactive=True
    if args.command=='prepare':
        if not args.metadata and not args.interactive: raise WorkflowError('--interactive oder geprüfte --metadata angeben')
        if args.interactive:
            from autobookkeeping import guided
            template=args.metadata or args.review.parent/'metadaten.json'
            payload=guided.receipt(json.loads(template.read_bytes()))
            from autobookkeeping.archive import atomic,encoded,outside
            args.metadata=outside(ROOT,args.review.parent/'metadaten-geprueft.json');atomic(args.metadata,encoded(payload))
    if args.command=='invalidieren' and args.interactive:
        from autobookkeeping.archive import encoded,sha
        with FileLock(ROOT/'output/archive.lock',timeout=0):
            archive=Archive(ROOT);archive.verify();reviewed=archive.catalog()
            args.reviewed_sha256=sha(encoded(reviewed))
            for rid in args.ids:
                row=reviewed.get('records',{}).get(rid,{}).get('current',{})
                if row.get('kind')!='expense':raise WorkflowError('Erfasste Originalausgabe erforderlich')
                from autobookkeeping.receipts import supplier
                print(rid, row.get('date'), row.get('gross'), row.get('currency'), supplier(row))
        args.reason=input('Begründung für das Ungültigerklären: ').strip()
        print('Betroffene Ausgaben:', ', '.join(args.ids), '\nBegründung:', args.reason)
        args.approved=input('Diese Ausgaben ungültig erklären? FREIGEBEN eingeben: ').strip()=='FREIGEBEN'
    with Publication(ROOT, "receipt " + args.command, enabled=args.command in ['prepare', 'book', 'discard', 'invalidieren']) as publication:
        with FileLock(ROOT/"output/archive.lock",timeout=0):
            workflow=LocalInvoices(Archive(ROOT));receipts=Receipts(workflow)
            if workflow.journal.exists():raise WorkflowError("Offene Archivtransaktion zuerst mit local_invoice.py recover abschließen")
            if args.command=="inspect":
                base=Path(os.environ.get("LOCALAPPDATA") or Path.home()/".cache")/"BuchhaltungTool"/"belegpruefung"
                target=args.output or base/uuid.uuid4().hex
                result=receipts.inspect(args.path,target,args.original_id)
            elif args.command=="prepare":result=receipts.prepare(args.review,args.metadata)
            elif args.command=="book":result=receipts.book(args.id,args.revision,args.approved)
            elif args.command=="discard":result=receipts.discard(args.id)
            elif args.command=='invalidieren':
                from autobookkeeping.invalidations import invalidate
                if args.interactive and sha(encoded(workflow.archive.catalog()))!=args.reviewed_sha256:
                    raise WorkflowError('Bestand nach Prüfung geändert; erneut prüfen und freigeben')
                result=invalidate(workflow,args.ids,args.reason,args.approved)
            else:
                receipts.archive.verify();drafts=receipts.archive.catalog().get("local_expense_drafts",{})
                result=receipts.summary(drafts[args.id]["current"]) if args.command=="show" else {
                    "ok":True,"drafts":[receipts.summary(v["current"]) for v in drafts.values() if v["current"]["status"]=="test_draft"]}
    if publication.enabled: result["publication"] = publication.result
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    try:main()
    except WorkflowError as exc:
        print(json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False));sys.exit(1)
    except Exception as exc:
        from autobookkeeping.diagnostics import failure
        print(json.dumps(failure(exc,ROOT),ensure_ascii=False));sys.exit(1)
