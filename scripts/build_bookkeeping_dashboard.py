"""Deterministic offline HTML; a commit uses the staged index, never unstaged data."""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOL / "src"))
from autobookkeeping.workspace import data_root
from filelock import FileLock
from autobookkeeping.archive import Archive, atomic, sha
from autobookkeeping.dashboard import html, index_blob, index_catalog, projection

CODE = ["scripts/build_bookkeeping_dashboard.py", "scripts/dashboard_view.html",
        "scripts/bookkeeping_action.py", "scripts/publish_bookkeeping.py", "scripts/homeoffice.py",
        "scripts/receipt.py", "scripts/local_invoice.py", "scripts/bookkeeping_archive.py",
        "scripts/backup_register.py", "scripts/reconcile_ebay.py",
        *["src/autobookkeeping/"+name+".py" for name in
          ("__init__", "workspace", "archive", "audit_trail", "inspection_export", "backups", "reconciliation", "checklist", "handover", "dashboard", "adjustments", "cashflow", "local_invoices", "taxes", "ledger_validation", "receipts", "einvoices", "retention", "homeoffice", "publication", "timestamps", "models")]]


def git(repo, *args):
    from autobookkeeping.workspace import git as workspace_git, assert_git_root
    assert_git_root(repo)
    return workspace_git(repo, *args)


def build(repo: Path, staged=False, check=False, tool=None):
    tool = tool or TOOL
    target = repo / "dashboard.html"
    if (repo / "output/local-invoice-transaction.enc").exists():
        raise ValueError("Unterbrochene Archivtransaktion zuerst wiederherstellen")
    if staged:
        changed = git(repo, "diff", "--cached", "--name-only", "-z").decode().split("\0")
        if any(n == ".env" or n.startswith(".env.") for n in changed):
            raise ValueError("Passwort-/Zugangsdaten dürfen nicht eingecheckt werden")
        relevant = any(n in CODE or n in ("dashboard.html", "timestamp-status.json") or n.startswith("buchhaltung/") and not n.startswith("buchhaltung/nachweise/") and n not in ("buchhaltung/README.md", "buchhaltung/AGENTS.md") for n in changed)
        if not relevant and not check:
            return {"skipped": True}
        from autobookkeeping.workspace import assert_tool_clean
        if tool != repo: assert_tool_clean()
        else:
            for name in CODE:
                if git(repo, "hash-object", name).strip() != git(repo, "rev-parse", ":"+name).strip():
                    raise ValueError("Dashboard-Helfer enthält nicht vorgemerkte Änderungen: " + name)
        catalog, digest = index_catalog(repo)
        template = (tool / "scripts/dashboard_view.html").read_bytes()
    else:
        archive = Archive(repo); archive.verify(); catalog = archive.catalog()
        digest = sha((archive.root / "database.json.enc").read_bytes())
        template = (tool / "scripts/dashboard_view.html").read_bytes()
    from autobookkeeping.timestamps import dashboard_status
    snapshot=projection(catalog,digest)
    snapshot['timestamps']=dashboard_status(repo,staged)
    data = html(snapshot, template)
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
            if existing is not None and existing != indexed:
                raise ValueError("Lokale Dashboard-Änderung würde überschrieben; zuerst bewusst sichern oder verwerfen")
        atomic(target, data)
    if staged and not check:
        git(repo, "add", "--", "dashboard.html")
    return {"ok": True, "rows":len(projection(catalog,digest)["rows"]), "source_sha256":digest, "output":str(target), "staged":staged}


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
