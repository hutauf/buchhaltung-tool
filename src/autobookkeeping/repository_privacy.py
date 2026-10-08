"""Fail closed on unverified GitHub visibility; never log credentials."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

from autobookkeeping.local_invoices import WorkflowError


def github_repository(url: str) -> str | None:
    if url.startswith('git@github.com:'):
        path = url[len('git@github.com:'):]
    elif '://' in url:
        parsed = urlsplit(url)
        if parsed.hostname != 'github.com' or parsed.scheme not in ('https', 'ssh') or parsed.port:
            raise WorkflowError('Privatheitsprüfung unterstützt nur kanonische GitHub-Remotes')
        if (parsed.password or parsed.query or parsed.fragment
                or parsed.scheme == 'https' and parsed.username
                or parsed.scheme == 'ssh' and parsed.username not in (None, 'git')):
            raise WorkflowError('Remote darf keine Zugangswerte oder URL-Zusätze enthalten')
        path = parsed.path.lstrip('/')
    else:
        local = Path(url).resolve()
        if local.is_dir() and (local / 'HEAD').is_file() and (local / 'objects').is_dir():
            return None  # Explicit local bare repositories, used for offline development/tests.
        raise WorkflowError('GitHub-Remote oder vorhandenes lokales Bare-Repo erforderlich')
    path = path.removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+', path):
        raise WorkflowError('Ungültige GitHub-Repo-Adresse')
    return path


def github_token(repo: Path) -> str:
    settings = dotenv_values(repo / '.env')
    for name in ('GH_TOKEN', 'GITHUB_TOKEN'):
        value = os.environ.get(name) or settings.get(name)
        if value:
            return value
    environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    environment.update(GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    try:
        run = subprocess.run(['git', 'credential', 'fill'],
                             input=b'protocol=https\nhost=github.com\n\n', capture_output=True,
                             env=environment, timeout=20)
        values = dict(line.split('=', 1) for line in run.stdout.decode('utf8').splitlines() if '=' in line)
        if run.returncode == 0 and values.get('password'):
            return values['password']
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        pass
    raise WorkflowError('GitHub-Metadatenzugriff fehlt: vorhandene Git-Credentials oder GH_TOKEN/GITHUB_TOKEN mit lesendem Repo-Metadatenzugriff verwenden')


def assert_private_remote(url: str, repo: Path) -> dict:
    name = github_repository(url)
    if name is None:
        return {'private': None, 'verification': 'local_bare_repository'}
    token = github_token(repo)
    try:
        response = httpx.get('https://api.github.com/repos/' + name,
                             headers={'Authorization': 'Bearer ' + token,
                                      'Accept': 'application/vnd.github+json'},
                             timeout=20, follow_redirects=False)
        if response.status_code != 200:
            raise WorkflowError('GitHub-Privatheit nicht bestätigt; Zugriff, Verbindung oder umbenannten Remote prüfen')
        metadata = response.json()
    except (httpx.HTTPError, ValueError):
        raise WorkflowError('GitHub-Privatheit wegen API-/Verbindungsfehler nicht bestätigt') from None
    if (not isinstance(metadata, dict) or not isinstance(metadata.get('full_name'), str)
            or metadata.get('full_name', '').lower() != name.lower()
            or metadata.get('private') is not True or metadata.get('visibility') != 'private'):
        raise WorkflowError('Datenrepo ist nicht als privates GitHub-Repo bestätigt; Veröffentlichung gesperrt')
    return {'private': True, 'verification': 'github_api'}
