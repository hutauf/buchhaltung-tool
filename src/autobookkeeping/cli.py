"""Single local entry point; writes use the existing private publication pipeline."""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path

ROUTES = {
    "rechnung": ("local_invoice.py", [], "Lokale Rechnungen und Korrekturen"),
    "beleg": ("receipt.py", [], "Belege lesen, vormerken und nach Freigabe buchen"),
    "zahlung": ("local_invoice.py", [], "Zahlungsnachweise erfassen oder berichtigen"),
    "archiv": ("bookkeeping_archive.py", [], "Verschluesseltes Archiv und Klartextexport ausserhalb des Repos"),
    "pruefen": ("bookkeeping_archive.py", ["verify"], "Archivintegritaet pruefen"),
    "dashboard": ("build_bookkeeping_dashboard.py", [], "Anonymisierte HTML-Uebersicht erzeugen"),
    "sicherung": ("bookkeeping_archive.py", [], "Sicherung exportieren, pruefen oder wiederherstellen"),
    "veroeffentlichen": ("publish_bookkeeping.py", [], "Git-/Zeitnachweis-Pipeline pruefen und fortsetzen"),
    "homeoffice": ("homeoffice.py", [], "Homeoffice-Tage pruefen und nach Freigabe speichern"),
    "ebay": ("get_ebay_orders.py", [], "eBay-Bestellungen lesen"),
    "vine": ("vine_backend.py", [], "Vine-Abstimmung"),
    "checkliste": ("checklist.py", [], "Historische operative Checkliste"),
    "aktion": ("bookkeeping_action.py", [], "Kopierten Dashboard-Befehl ausfuehren"),
}


def command(argv):
    group = argv[0]
    script, prefix, _ = ROUTES[group]
    tail = argv[1:]
    if group == "zahlung":
        aliases = {"erfassen":"cash-record", "berichtigen":"cash-void"}
        if not tail or tail[0] not in aliases:
            if tail in ([], ["--help"], ["-h"]):
                return None
            raise ValueError("zahlung: erfassen oder berichtigen angeben")
        tail = [aliases[tail[0]], *tail[1:]]
    if group == "sicherung":
        aliases = {"export":"cd-export", "pruefen":"cd-verify", "wiederherstellen":None}
        if not tail or tail[0] not in aliases:
            if tail in ([], ["--help"], ["-h"]): return None
            raise ValueError("sicherung: export, pruefen oder wiederherstellen angeben")
        if tail[0] == "wiederherstellen": script = "restore_backup.py"; tail = tail[1:]
        else: tail = [aliases[tail[0]], *tail[1:]]
    return script, [*prefix, *tail]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="Lokale verschluesselte Buchhaltung")
    parser.add_argument("bereich", nargs="?", choices=ROUTES, help="; ".join(k+": "+v[2] for k,v in ROUTES.items()))
    if not argv or argv[0] in ("--help", "-h"):
        parser.print_help(); return 0
    parser.parse_args([argv[0]])
    try: route = command(argv)
    except ValueError as exc: parser.error(str(exc))
    if route is None:
        print("buchhaltung zahlung erfassen --metadata DATEI --approved\nbuchhaltung zahlung berichtigen ID --reason GRUND --approved" if argv[0] == "zahlung" else
              "buchhaltung sicherung export --output NEUER_ORDNER\nbuchhaltung sicherung pruefen ORDNER\nbuchhaltung sicherung wiederherstellen ORDNER --password-file ENV --output NEUER_ORDNER")
        return 0
    script, arguments = route
    tool = Path(__file__).resolve().parents[2]
    from autobookkeeping.workspace import git_environment
    return subprocess.run([sys.executable, "-X", "utf8", str(tool/"scripts"/script), *arguments],
                          cwd=tool, env=git_environment()).returncode


if __name__ == "__main__":
    raise SystemExit(main())
