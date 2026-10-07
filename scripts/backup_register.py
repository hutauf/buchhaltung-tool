"""Registered exports, actual medium readback and isolated restore tests."""
import argparse
import json
import sys
from pathlib import Path
TOOL=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOL/'src'))
from filelock import FileLock
from autobookkeeping.workspace import data_root
from autobookkeeping.archive import Archive, cd_verify
from autobookkeeping.local_invoices import LocalInvoices
from autobookkeeping.publication import Publication
from autobookkeeping.backups import export, register, confirm, restore_test, public_status


def main():
    parser=argparse.ArgumentParser(description='Sicherungsregister; kein automatisches Brennen')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('status')
    p=sub.add_parser('export');p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('pruefen');p.add_argument('directory',type=Path)
    p=sub.add_parser('registrieren');p.add_argument('directory',type=Path)
    for action in ('bestaetigen','test'):
        p=sub.add_parser(action);p.add_argument('--id',required=True);p.add_argument('--directory',type=Path,required=True)
        if action=='bestaetigen':
            p.add_argument('--medium',required=True);p.add_argument('--written',action='store_true');p.add_argument('--approved',action='store_true')
    args=parser.parse_args(); root=data_root(); (root/'output').mkdir(exist_ok=True)
    writes=args.command in ('export','registrieren','bestaetigen','test')
    with Publication(root,'backup '+args.command,enabled=writes) as publication:
        with FileLock(root/'output/archive.lock',timeout=0):
            if (root/'output/local-invoice-transaction.enc').exists(): raise ValueError('Offene Transaktion zuerst wiederaufnehmen')
            archive=Archive(root);workflow=LocalInvoices(archive)
            if args.command=='status': archive.verify(); result=dict(ok=True,**public_status(archive.catalog()))
            elif args.command=='pruefen':result=cd_verify(args.directory)
            elif args.command=='export':result=export(workflow,args.output)
            elif args.command=='registrieren':result=register(workflow,args.directory)
            elif args.command=='test':result=restore_test(workflow,args.id,args.directory)
            else:result=confirm(workflow,args.id,args.directory,args.medium,args.written,args.approved)
    print(json.dumps(dict(result,publication=publication.result),ensure_ascii=False,indent=2))
    return int(result.get('ok') is False)


if __name__=='__main__':
    try: sys.exit(main())
    except Exception as exc:
        print(json.dumps({'ok':False,'error_type':type(exc).__name__, 'hint':'Sicherungs-/Publikationsstatus prüfen; vorhandenen Export bei Bedarf registrieren'}));sys.exit(1)
