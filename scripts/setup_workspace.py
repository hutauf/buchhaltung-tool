"""Create/connect a private data checkout and install local repository guards."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / 'src'))
from autobookkeeping.workspace import assert_git_root, assert_data_repo, git, git_environment
from autobookkeeping.archive import atomic, encoded


def install_hooks():
    data = assert_data_repo(TOOL / 'daten')
    try: existing = git(TOOL, 'config', '--get', 'core.hooksPath').decode().strip()
    except subprocess.CalledProcessError: existing = ''
    if existing not in ('', '.githooks'):
        raise ValueError('Individuelle Tool-Hooks zuerst bewusst integrieren; nichts ersetzt')
    if not existing and (TOOL / '.git/hooks/pre-commit').exists():
        raise ValueError('Vorhandenen individuellen Tool-Hook zuerst bewusst integrieren; nichts ersetzt')
    try: data_hooks = git(data, 'config', '--get', 'core.hooksPath').decode().strip()
    except subprocess.CalledProcessError: data_hooks = ''
    if data_hooks:
        raise ValueError('Individuellen Daten-hooksPath zuerst bewusst integrieren; nichts ersetzt')
    git(TOOL, 'config', '--local', 'core.hooksPath', '.githooks')
    git(TOOL, 'config', '--local', 'bookkeeping.allowToolCommit', 'false')
    directory = Path(git(data, 'rev-parse', '--git-path', 'hooks').decode().strip())
    if not directory.is_absolute(): directory = data / directory
    python = TOOL / '.venv/Scripts/python.exe' if sys.platform == 'win32' else TOOL / '.venv/bin/python'
    hook = ("#!/bin/sh\n# bookkeeping-workspace generated hook\nexec '" + python.as_posix() + "' -X utf8 '" +
            (TOOL / 'scripts/build_bookkeeping_dashboard.py').as_posix() + "' --staged\n").encode()
    destination = directory / 'pre-commit'
    if destination.exists() and b'bookkeeping-workspace generated hook' not in destination.read_bytes():
        raise ValueError('Vorhandener eigener Daten-Hook bleibt unverändert; bewusst integrieren')
    atomic(destination, hook); destination.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description='Unabhängiges privates Datenrepo unter daten/ einrichten')
    parser.add_argument('--data-url'); parser.add_argument('--hooks-only', action='store_true')
    args = parser.parse_args(); assert_git_root(TOOL)
    data = TOOL / 'daten'
    if args.hooks_only: install_hooks(); print('Lokale Git-Sperren installiert'); return
    if not args.data_url: raise ValueError('--data-url für das private GitHub-Repo angeben')
    if not data.exists():
        subprocess.run(['git','clone','--',args.data_url,str(data)], env=git_environment(), check=True)
    assert_git_root(data)
    if not (data / '.bookkeeping-data.json').exists():
        atomic(data / '.bookkeeping-data.json', encoded({'version':1,'role':'data'}))
        atomic(data / '.gitignore', b'.env\n.env.*\noutput/\ndownloads/\n')
        atomic(data / '.gitattributes', b'buchhaltung/** -text\nmigration/** -text\n/*.json -text\n*.enc -text\ndashboard.html text eol=lf\n')
        atomic(data / 'AGENTS.md', (TOOL / 'docs/data-AGENTS.md').read_bytes())
        atomic(data / 'buchhaltung/AGENTS.md', (TOOL / 'docs/data-AGENTS.md').read_bytes())
        atomic(data / 'buchhaltung/README.md', (TOOL / 'docs/data-README.md').read_bytes())
        atomic(data / 'verfahrensdokumentation.md', (TOOL / 'docs/betriebliche-ergaenzung-vorlage.md').read_bytes())
    try: configured = git(data, 'remote', 'get-url', '--push', 'origin').decode().strip()
    except subprocess.CalledProcessError:
        git(data,'remote','add','origin',args.data_url); configured=args.data_url
    if configured != args.data_url: raise ValueError('Bestehender Daten-Remote weicht ab; keine stille Änderung')
    atomic(data / 'workspace.json', encoded({'version':1,'expected_push_url':args.data_url}))
    install_hooks()
    print(json.dumps({'ok':True,'data':str(data),'next':'daten/.env lokal einrichten; danach Archiv initialisieren oder Migration prüfen'},ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc) if type(exc) is ValueError else type(exc).__name__})); sys.exit(1)
