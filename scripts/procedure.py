"""Interview and private operating documentation. Never reads passwords for the interview."""
import argparse
import json
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / 'src'))
from filelock import FileLock
from autobookkeeping.archive import Archive, atomic, outside
from autobookkeeping.local_invoices import LocalInvoices, today
from autobookkeeping.publication import Publication
from autobookkeeping.workspace import data_root
from autobookkeeping import procedure


def main():
    parser = argparse.ArgumentParser(description='Private Verfahrensdokumentation geführt beschreiben')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('fragen')
    sub.add_parser('status')
    p = sub.add_parser('vorbereiten')
    p.add_argument('--answers', type=Path); p.add_argument('--interactive', action='store_true')
    p.add_argument('--effective-from', default=today()); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('speichern')
    p.add_argument('--answers', type=Path, required=True); p.add_argument('--revision', required=True)
    p.add_argument('--approved', action='store_true')
    p = sub.add_parser('anzeigen'); p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'fragen':
        print(procedure.interview_prompt()); return
    if args.command == 'vorbereiten' and bool(args.answers) == bool(args.interactive):
        parser.error('Genau --answers DATEI oder --interactive angeben')
    root = data_root(); (root / 'output').mkdir(exist_ok=True)
    with Publication(root, 'Update private operating procedure', enabled=args.command == 'speichern') as publication:
        with FileLock(root / 'output/archive.lock', timeout=0):
            archive = Archive(root); archive.verify()
            if args.command == 'status': result = procedure.public_status(archive.catalog())
            elif args.command == 'vorbereiten':
                if args.interactive:
                    from autobookkeeping.guided import ask, choice
                    answers = {}
                    current = archive.catalog().get('operating_procedure', {}).get('current') or {}
                    for key, question in procedure.QUESTIONS.items():
                        old = current.get('answers', {}).get(key, {})
                        print('\n' + question)
                        state = choice('Status', ('beschrieben', 'offen', 'entfaellt'),
                                       {'documented': 'beschrieben', 'open': 'offen', 'not_applicable': 'entfaellt'}.get(old.get('status'), 'offen'))
                        answers[key] = {'status': {'beschrieben': 'documented', 'offen': 'open', 'entfaellt': 'not_applicable'}[state],
                                        'text': ask('Tatsächliches Vorgehen / offene Frage / Begründung', old.get('text') or None, optional=state == 'offen') or ''}
                else: answers = json.loads(outside(root, args.answers).read_text(encoding='utf8'))
                result = procedure.prepare(archive, answers, args.effective_from, args.output)
            elif args.command == 'speichern':
                body = json.loads(outside(root, args.answers).read_text(encoding='utf8'))
                result = procedure.save(LocalInvoices(archive), body, args.revision, args.approved)
            else:
                current = archive.catalog().get('operating_procedure', {}).get('current')
                if not current: raise ValueError('Noch keine Betriebsangaben gespeichert; zuerst vorbereiten')
                target = outside(root, args.output)
                if target.exists(): raise ValueError('Ausgabeordner muss neu sein')
                atomic(target / 'verfahrensdokumentation.md', procedure.markdown(current).encode('utf8'))
                result = {'ok': True, 'output': str(target)}
    print(json.dumps(dict(result, publication=publication.result), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        from autobookkeeping.diagnostics import failure
        print(json.dumps(failure(exc, TOOL / 'daten'), ensure_ascii=False)); sys.exit(1)
