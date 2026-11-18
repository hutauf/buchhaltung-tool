"""Deterministic offline HTML; a commit uses the staged index, never unstaged data."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "src"))
from autobookkeeping.workspace import data_root
from filelock import FileLock
from autobookkeeping.archive import Archive, atomic, encoded, sha
from autobookkeeping.dashboard import html, index_blob, index_catalog, projection

CODE = ["scripts/build_bookkeeping_dashboard.py", "scripts/dashboard_view.html", "docs/verfahrensdokumentation.md",
        "scripts/bookkeeping_action.py", "scripts/publish_bookkeeping.py", "scripts/homeoffice.py",
        "scripts/receipt.py", "scripts/local_invoice.py", "scripts/bookkeeping_archive.py", "scripts/password.py",
        "scripts/backup_register.py", "scripts/reconcile_ebay.py", "scripts/procedure.py", "scripts/annual_report.py", "scripts/datev_export.py",
        *["src/autobookkeeping/"+name+".py" for name in
        ("__init__", "password_check", "guided", "diagnostics", "workspace", "repository_privacy", "archive", "audit_trail", "inspection_export", "invalidations", "backups", "reconciliation", "procedure", "annual_report", "datev_export", "datev_validation", "checklist", "handover", "dashboard", "adjustments", "cashflow", "local_invoices", "local_preparation", "taxes", "ledger_validation", "receipts", "einvoices", "retention", "homeoffice", "publication", "timestamps", "models")]]


def git(repo, *args):
    from autobookkeeping.workspace import git as workspace_git, assert_git_root
    assert_git_root(repo)
    return workspace_git(repo, *args)


def source_binding(repo, tool, staged):
    """Bind a committed public projection to archive bytes and generator sources.

    Used only for proof-only changes: Git must also report every archive path
    unchanged from HEAD. This is not a persistent archive-verification cache.
    """
    names = ('buchhaltung/database.json.enc', 'buchhaltung/manifest.json', 'buchhaltung/key.json')
    return sha(encoded({
        'version': 1,
        'archive': {name: sha(index_blob(repo, name) if staged else (repo / name).read_bytes()) for name in names},
        'generator': {name: sha((tool / name).read_bytes()) for name in CODE},
    }))


def proof_path(name):
    import re
    return bool(re.fullmatch(r'buchhaltung/nachweise/[a-f0-9]{40}(?:[a-f0-9]{24})?\.json(?:\.ots(?:\.bak)?)?', name))


def projection_digest(snapshot):
    # The proof counts are recalculated; everything else must remain byte-bound.
    return sha(encoded({key: value for key, value in snapshot.items()
                        if key not in ('timestamps', 'build_projection_sha256')}))


def previous_projection(repo, binding):
    """Read only committed generated data, never a user-edited/staged HTML file."""
    try:
        data = git(repo, 'show', 'HEAD:dashboard.html')
        marker = b'<script id="bookkeeping-data" type="application/json">'
        if data.count(marker) != 1:
            return None
        snapshot = json.loads(data.split(marker, 1)[1].split(b'</script>', 1)[0])
        if (snapshot.get('build_source_sha256') == binding
                and snapshot.get('build_projection_sha256') == projection_digest(snapshot)):
            return snapshot
    except (subprocess.CalledProcessError, ValueError, KeyError, IndexError, AttributeError):
        pass
    return None


def build(repo: Path, staged=False, check=False, tool=None):
    tool = tool or TOOL
    target = repo / "dashboard.html"
    if (repo / "output/local-invoice-transaction.enc").exists():
        raise ValueError("Unterbrochene Archivtransaktion zuerst wiederherstellen")
    snapshot = None
    if staged:
        changed = git(repo, "diff", "--cached", "--name-only", "-z").decode().split("\0")
        if any(n == ".env" or n.startswith(".env.") for n in changed):
            raise ValueError("Passwort-/Zugangsdaten dürfen nicht eingecheckt werden")
        # Setup commits the operating document before the encrypted archive exists.
        # Once a database is staged, operating-document changes rebuild the view.
        operating_change = "verfahrensdokumentation.md" in changed and bool(
            git(repo, 'ls-files', '--stage', '--', 'buchhaltung/database.json.enc').strip())
        proof_only = any(proof_path(n) or n == 'timestamp-status.json' for n in changed) and all(
            not n or proof_path(n) or n in ('timestamp-status.json', 'dashboard.html') for n in changed)
        relevant = proof_only or operating_change or any(n in CODE or n in ("dashboard.html", "timestamp-status.json") or n.startswith("buchhaltung/") and not n.startswith("buchhaltung/nachweise/") and n not in ("buchhaltung/README.md", "buchhaltung/AGENTS.md") for n in changed)
        if not relevant and not check:
            return {"skipped": True}
        from autobookkeeping.workspace import assert_tool_clean
        if tool != repo: assert_tool_clean()
        else:
            for name in CODE:
                if git(repo, "hash-object", name).strip() != git(repo, "rev-parse", ":"+name).strip():
                    raise ValueError("Dashboard-Helfer enthält nicht vorgemerkte Änderungen: " + name)
        binding = source_binding(repo, tool, True)
        if proof_only:
            snapshot = previous_projection(repo, binding)
        if snapshot is None:
            archive=Archive(repo)
            catalog, digest = index_catalog(repo,archive=archive)
        template = (tool / "scripts/dashboard_view.html").read_bytes()
    else:
        archive = Archive(repo); archive.verify(); catalog = archive.catalog()
        digest = sha((archive.root / "database.json.enc").read_bytes())
        binding = source_binding(repo, tool, False)
        template = (tool / "scripts/dashboard_view.html").read_bytes()
    from autobookkeeping.timestamps import dashboard_status
    reused_projection = snapshot is not None
    if snapshot is None:
        snapshot=projection(catalog,digest)
        from autobookkeeping.password_check import descriptor
        wrapper=index_blob(repo,'buchhaltung/key.json') if staged else archive.key_path.read_bytes()
        snapshot['password_check']=descriptor(archive.password,wrapper)
    snapshot['build_source_sha256'] = binding
    snapshot['timestamps']=dashboard_status(repo,staged)
    snapshot['build_projection_sha256'] = projection_digest(snapshot)
    procedure=(tool/'docs/verfahrensdokumentation.md').read_bytes()
    operating_present=bool(git(repo,'ls-files','--stage','--','verfahrensdokumentation.md').strip()) if staged else (repo/'verfahrensdokumentation.md').is_file()
    data = html(snapshot, template, procedure, operating_present)
    existing = target.read_bytes() if target.exists() else None
    if check:
        if existing != data or staged and index_blob(repo, "dashboard.html") != data:
            raise ValueError("Dashboard ist nicht aktuell zum geprüften Bestand")
    elif existing != data:
        if staged:
            try:
                indexed = index_blob(repo, "dashboard.html")
            except subprocess.CalledProcessError:
                indexed = None
            # A checkout may normalize CRLF even when Git reports no user edit.
            # Preserve all content changes; only line-ending conversion is equivalent.
            if existing is not None and (indexed is None or
                    existing.replace(b'\r\n', b'\n') != indexed.replace(b'\r\n', b'\n')):
                raise ValueError("Lokale Dashboard-Änderung würde überschrieben; zuerst bewusst sichern oder verwerfen")
        atomic(target, data)
    if staged and not check:
        git(repo, "add", "--", "dashboard.html")
    return {"ok": True, "rows":len(snapshot['rows']), "source_sha256":snapshot['source_sha256'],
            "output":str(target), "staged":staged, "reused_projection":reused_projection}


def main():
    parser = argparse.ArgumentParser(description="Anonymisierte Offline-Bestandsübersicht erzeugen")
    parser.add_argument("--staged", action="store_true"); parser.add_argument("--check", action="store_true")
    args = parser.parse_args(); ROOT = data_root(); (ROOT / "output").mkdir(exist_ok=True)
    with FileLock(ROOT / "output/archive.lock", timeout=0):
        result = build(ROOT, args.staged, args.check)
    print("Dashboard: " + ("keine relevanten Änderungen" if result.get("skipped") else str(result["rows"])+" Belege · "+result["output"]))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Authenticated decryption/HTTP errors must not leak secret values.
        print("Dashboard-Prüfung fehlgeschlagen: " + (str(exc) if type(exc) is ValueError else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
