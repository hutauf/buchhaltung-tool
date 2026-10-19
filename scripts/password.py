"""Local password setup and memory check; never create a browser verifier."""
from __future__ import annotations
import argparse
import getpass
import json
import sys
import warnings
from pathlib import Path
TOOL=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(TOOL/'src'))
from autobookkeeping.archive import Archive, unwrap_key
from autobookkeeping.workspace import data_root, assert_data_repo
from autobookkeeping.local_invoices import WorkflowError


def secret(label):
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        try: return getpass.getpass(label)
        except getpass.GetPassWarning:
            raise WorkflowError('Passwortprüfung benötigt ein Terminal mit verdeckter Eingabe; keine Passwortargumente oder sichtbare Eingabe verwenden') from None


def run(command):
    root=data_root();path=root/'.env';archive=Archive(root)
    if command=='einrichten':
        assert_data_repo(root,remote=True)
        if archive.key_path.exists(): raise WorkflowError('Archiv existiert bereits. Passwort nicht durch Ändern der .env ersetzen; mit passwort pruefen testen.')
        from dotenv import dotenv_values,set_key
        if dotenv_values(path).get('ENCRYPTION_PASSWORD'): raise WorkflowError('Passwort bereits hinterlegt. Wert erhalten; kein Passwort überschrieben.')
        first=secret('Neues Archivpasswort (mindestens 16 Zeichen, Passwortmanager empfohlen): ')
        if len(first)<16: raise WorkflowError('Bitte eine Passphrase mit mehreren Wörtern oder ein zufälliges Passwort mit mindestens 16 Zeichen verwenden')
        if first!=secret('Zur Bestätigung erneut eingeben: '): raise WorkflowError('Eingaben stimmen nicht überein')
        if input('Passwort unabhängig gesichert? Zum Bestätigen GESICHERT eingeben: ').strip()!='GESICHERT':
            raise WorkflowError('Abgebrochen. Erst Passwort unabhängig sichern; ohne Passwort ist keine Wiederherstellung möglich.')
        path.touch(exist_ok=True);set_key(str(path),'ENCRYPTION_PASSWORD',first,quote_mode='always')
        try: path.chmod(0o600)
        except OSError: pass
        return {'ok':True,'hint':'Passwort lokal hinterlegt. Nach archiv init mit passwort pruefen aus der getrennten Sicherung testen. .env bleibt außerhalb von Git.'}
    candidate=secret('Archivpasswort aus Erinnerung / getrennter Sicherung: ')
    # Verify the entered password against the real key wrapper, never just .env equality.
    unwrap_key(archive.key_path.read_bytes(),candidate)
    return {'ok':True,'hint':'Passwort öffnet den Datenschlüssel. Eingabe nicht gespeichert. Dies ersetzt keinen vollständigen Wiederherstellungstest.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description='Passwort lokal einrichten oder verdeckt prüfen; keine Datenbuchung')
    p.add_argument('command',choices=('einrichten','pruefen'));args=p.parse_args()
    try: print(json.dumps(run(args.command),ensure_ascii=False))
    except WorkflowError as exc: print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));sys.exit(1)
    except Exception as exc:
        from autobookkeeping.diagnostics import failure
        print(json.dumps(failure(exc,TOOL/'daten'),ensure_ascii=False));sys.exit(1)
