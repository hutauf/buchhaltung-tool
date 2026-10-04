"""Separate code and data roots; Git must never fall back to a parent repo."""
from __future__ import annotations
import json
import os
import subprocess
from pathlib import Path
from autobookkeeping.local_invoices import WorkflowError

TOOL_ROOT = Path(__file__).resolve().parents[2]


def git_environment():
    # Inherited Git hooks export index/directory variables belonging to their repo.
    return {k:v for k,v in os.environ.items() if not k.startswith('GIT_') or k in ('GIT_SSH_COMMAND', 'GIT_TERMINAL_PROMPT')}


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], env=git_environment(), stderr=subprocess.PIPE, timeout=60)


def assert_git_root(repo):
    repo = Path(repo).resolve()
    if not (repo / '.git').exists(): raise WorkflowError('Eigenständiges Daten-Git-Repo fehlt; kein Rückgriff auf das Toolrepo')
    if Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != repo:
        raise WorkflowError('Git-Wurzel stimmt nicht mit dem Datenordner überein')
    return repo


def assert_data_repo(repo, remote=False):
    repo = assert_git_root(repo)
    if (repo / '.bookkeeping-tool.json').exists():
        raise WorkflowError('Toolrepo ist kein Buchhaltungsziel')
    marker = repo / '.bookkeeping-data.json'
    if not marker.is_file() or json.loads(marker.read_bytes()).get('role') != 'data':
        raise WorkflowError('Kein freigegebenes Datenrepo; Buchhaltungs-Git im Toolrepo gesperrt')
    if remote:
        configuration = json.loads((repo / 'workspace.json').read_bytes())
        expected = configuration.get('expected_push_url')
        urls = git(repo, 'remote', 'get-url', '--push', '--all', 'origin').decode().splitlines()
        upstream = git(repo, 'rev-parse', '--abbrev-ref', '@{upstream}').decode().strip()
        if not expected or urls != [expected] or not upstream.startswith('origin/'):
            raise WorkflowError('Push-Ziel stimmt nicht mit dem freigegebenen privaten Repo überein')
        try: public_urls = git(tool_root(), 'remote', 'get-url', '--push', '--all', 'origin').decode().splitlines()
        except subprocess.CalledProcessError: public_urls = []
        if any(repository_identity(url) == repository_identity(expected) for url in public_urls):
            raise WorkflowError('Tool- und Datenrepo müssen verschiedene Push-Ziele besitzen')
    return repo


def data_root():
    return assert_data_repo(TOOL_ROOT / 'daten')


def tool_root():
    return TOOL_ROOT


def repository_identity(url):
    from urllib.parse import urlsplit
    import re
    match = re.fullmatch(r'(?:[^@]+@)?([^/:]+):(.+)', url)
    if '://' in url:
        parsed = urlsplit(url)
        value = (parsed.hostname or '') + '/' + parsed.path.lstrip('/')
    elif match and '@' in url:
        value = match[1] + '/' + match[2]
    else: value = str(Path(url).resolve())
    return value.removesuffix('.git').rstrip('/').lower()


def assert_tool_clean():
    root = assert_git_root(tool_root())
    if git(root, 'status', '--porcelain', '--untracked-files=all').strip():
        raise WorkflowError('Toolrepo enthält ungeprüfte Änderungen; zuerst Toolversion veröffentlichen')
    return git(root, 'rev-parse', 'HEAD').decode().strip()
