"""Export only: never invoke Publication or write to the bookkeeping repository."""
import argparse
import json
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL/'src'))
from filelock import FileLock
from autobookkeeping.archive import Archive
from autobookkeeping.datev_export import export
from autobookkeeping.workspace import data_root


def main():
    parser = argparse.ArgumentParser(description='DATEV-CSV mit Begleitbericht als ZIP exportieren; keine Buchung')
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--advisor', required=True, help='Echte Beraternummer des DATEV-Empfängers')
    parser.add_argument('--client', required=True, help='Echte Mandantennummer des DATEV-Empfängers')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); root = data_root(); (root/'output').mkdir(exist_ok=True)
    with FileLock(root/'output/archive.lock', timeout=0):
        if (root/'output/local-invoice-transaction.enc').exists(): raise ValueError('Offene Archivtransaktion zuerst wiederaufnehmen')
        result = export(Archive(root), args.year, args.advisor, args.client, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        from autobookkeeping.diagnostics import failure
        print(json.dumps(failure(exc, TOOL/'daten'), ensure_ascii=False)); sys.exit(1)
