"""Persistent sales-source check. No invoices, expenses or external writes."""
import argparse
import json
import sys
from pathlib import Path
TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL/'src'))
from filelock import FileLock
from autobookkeeping.workspace import data_root
from autobookkeeping.archive import Archive
from autobookkeeping.checklist import ChecklistStore
from autobookkeeping.config import load_settings
from autobookkeeping.ebay_client import EbayTradingClient
from autobookkeeping.publication import Publication
from autobookkeeping.reconciliation import scan, public_status, findings, explain


def main():
    parser=argparse.ArgumentParser(description='eBay-Verkaufsbestand per API prüfen; kein Gebühren-/Zahlungsimport')
    parser.add_argument('command', choices=('ebay','status','faelle','klaeren','wiederoeffnen'))
    parser.add_argument('--ref', help='Konkrete Referenz aus dem Dashboard oder faelle')
    parser.add_argument('--reason'); parser.add_argument('--approved', action='store_true')
    parser.add_argument('--interactive', action='store_true')
    parser.add_argument('--days', type=int, default=90)
    parser.add_argument('--save', action='store_true', help='Prüfnachweis verschlüsselt speichern, committen/pushen und OTS einreichen')
    parser.add_argument('--details', action='store_true', help='Lokale Vorgangsreferenzen anzeigen, keine Käuferdaten')
    parser.add_argument('--checklist', type=Path, help='Optional eine aktuelle externe operative Checkliste lesend vergleichen; keine Finanzdaten übernehmen')
    args=parser.parse_args(); root=data_root(); (root/'output').mkdir(exist_ok=True)
    if args.command!='ebay' and args.save: parser.error('--save gehört nur zum API-Abgleich')
    writing = args.save or args.command in ('klaeren','wiederoeffnen')
    if args.command in ('klaeren','wiederoeffnen') and not args.ref: parser.error('--ref erforderlich')
    with Publication(root, 'eBay sales reconciliation', enabled=writing) as publication:
        with FileLock(root/'output/archive.lock', timeout=0):
            if (root/'output/local-invoice-transaction.enc').exists(): raise ValueError('Offene Transaktion zuerst wiederaufnehmen')
            archive=Archive(root)
            if args.command=='status': archive.verify(); result=public_status(archive.catalog())
            elif args.command=='faelle':
                archive.verify(); result={'findings': findings(archive.catalog())}
            elif args.command in ('klaeren','wiederoeffnen'):
                if args.interactive:
                    from autobookkeeping.guided import ask, yes
                    archive.verify()
                    case = next((f for f in findings(archive.catalog()) if f['ref'] == args.ref), None)
                    if not case: raise ValueError('Abweichung fehlt oder wurde verändert; Fälle erneut anzeigen')
                    print(json.dumps(case, ensure_ascii=False, indent=2))
                    args.reason = ask('Warum weicht dieser Vorgang ab? / Grund der Wiederöffnung', args.reason)
                    args.approved = yes('Diesen Vermerk speichern? Er ändert keine Rechnung und keinen Betrag.')
                from autobookkeeping.local_invoices import LocalInvoices
                result=explain(LocalInvoices(archive),args.ref,args.reason,args.approved,args.command=='wiederoeffnen')
            else:
                checklist=ChecklistStore(args.checklist.resolve()).load() if args.checklist else ChecklistStore().load()
                result=scan(archive, EbayTradingClient(load_settings()), checklist, args.days, args.save)
                if not args.details: result.pop('rows', None)
    print(json.dumps(dict(ok=True, **result, publication=publication.result), ensure_ascii=False, indent=2))


if __name__=='__main__':
    try: main()
    except Exception as exc:
        from autobookkeeping.diagnostics import failure
        print(json.dumps(failure(exc,TOOL/'daten'),ensure_ascii=False));sys.exit(1)
