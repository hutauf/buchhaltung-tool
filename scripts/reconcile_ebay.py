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
from autobookkeeping.reconciliation import scan, public_status


def main():
    parser=argparse.ArgumentParser(description='eBay-Verkaufsbestand per API prüfen; kein Gebühren-/Zahlungsimport')
    parser.add_argument('command', choices=('ebay','status'))
    parser.add_argument('--days', type=int, default=90)
    parser.add_argument('--save', action='store_true', help='Prüfnachweis verschlüsselt speichern, committen/pushen und OTS einreichen')
    parser.add_argument('--details', action='store_true', help='Lokale Vorgangsreferenzen anzeigen, keine Käuferdaten')
    parser.add_argument('--checklist', type=Path, help='Optional eine aktuelle externe operative Checkliste lesend vergleichen; keine Finanzdaten übernehmen')
    args=parser.parse_args(); root=data_root(); (root/'output').mkdir(exist_ok=True)
    if args.command=='status' and args.save: parser.error('status ist nur lesend')
    with Publication(root, 'eBay sales reconciliation', enabled=args.save) as publication:
        with FileLock(root/'output/archive.lock', timeout=0):
            if (root/'output/local-invoice-transaction.enc').exists(): raise ValueError('Offene Transaktion zuerst wiederaufnehmen')
            archive=Archive(root)
            if args.command=='status': archive.verify(); result=public_status(archive.catalog())
            else:
                checklist=ChecklistStore(args.checklist.resolve()).load() if args.checklist else ChecklistStore().load()
                result=scan(archive, EbayTradingClient(load_settings()), checklist, args.days, args.save)
                if not args.details: result.pop('rows', None)
    print(json.dumps(dict(ok=True, **result, publication=publication.result), ensure_ascii=False, indent=2))


if __name__=='__main__':
    try: main()
    except Exception as exc:
        print(json.dumps({'ok':False,'error_type':type(exc).__name__, 'hint':'API-Zugang, Fenster und Veröffentlichen-Status prüfen; keine Buchung wurde durch den Abgleich angelegt'}));sys.exit(1)
