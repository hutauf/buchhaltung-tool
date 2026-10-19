"""Actionable public errors without exception bodies, URLs or credentials."""
from __future__ import annotations
import json
from pathlib import Path


def failure(exc, repo: Path | None = None) -> dict:
    from cryptography.exceptions import InvalidTag
    from autobookkeeping.local_invoices import WorkflowError
    import imaplib
    import httpx
    from filelock import Timeout
    error, hint = "Vorgang konnte nicht abgeschlossen werden.", "Eingaben prüfen und den Vorgang erneut prüfen, bevor du ihn wiederholst."
    if isinstance(exc, WorkflowError):
        error, hint = str(exc), 'Den genannten Prüfschritt durchführen; bereits gespeicherte Buchungen nicht nochmals anlegen.'
    elif isinstance(exc, InvalidTag):
        error, hint = "Archiv konnte nicht entschlüsselt werden.", "Archivpasswort mit buchhaltung passwort pruefen testen. Bei richtigem Passwort Sicherung und Integrität prüfen; keinen neuen Schlüssel erzeugen."
    elif isinstance(exc, FileNotFoundError):
        error, hint = "Eine benötigte Datei fehlt.", "Eingegebenen Datei- oder Ordnerpfad und die Einrichtung prüfen."
    elif isinstance(exc, PermissionError):
        error, hint = "Zugriff auf eine Datei oder einen Ordner verweigert.", "Zugriffsrechte und geöffnete Dateien prüfen."
    elif isinstance(exc, (Timeout, TimeoutError)):
        error, hint = "Der Vorgang ist noch belegt oder hat das Zeitlimit überschritten.", "Andere laufende Buchhaltungsbefehle beenden lassen und Veröffentlichungsstatus prüfen."
    elif isinstance(exc, json.JSONDecodeError):
        error, hint = "Eine Eingabedatei enthält ungültiges JSON.", "Den geführten Dialog (--interactive) verwenden oder die Eingabedatei korrigieren."
    elif isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        error = f"Der angebundene Dienst meldet HTTP {status}."
        hint = "Zugangsdaten und Berechtigungen der ausgewählten Anbindung prüfen." if status in (401,403) else "Verfügbarkeit der Anbindung prüfen; später erneut versuchen."
    elif isinstance(exc, httpx.RequestError):
        error, hint = "Die Verbindung zum angebundenen Dienst ist fehlgeschlagen.", "Internetverbindung und konfigurierte Anbindung prüfen; später erneut versuchen."
    elif isinstance(exc, imaplib.IMAP4.error):
        error, hint = 'Der Postfachzugriff ist fehlgeschlagen.', 'GMX-IMAP-Zugang und gegebenenfalls das App-Passwort prüfen; die Mailprüfung anschließend erneut starten.'
    elif isinstance(exc, ValueError):
        error, hint = 'Eingabe oder Dateiformat ist ungültig.', 'Datum, Zahlen und Pflichtfelder im geführten Dialog prüfen; bei vorhandenen Archivdateien auch die Integrität mit buchhaltung pruefen testen.'
    elif isinstance(exc, (EOFError, KeyboardInterrupt)):
        error, hint = "Eingabe abgebrochen.", "Interaktive Befehle in einem Terminal ausführen. Ohne Abschlussbestätigung wird nicht gebucht."
    result = {"ok": False, "error": error, "error_type": type(exc).__name__, "hint": hint}
    if repo is not None and (repo / 'output/publication.json').is_file():
        result['publication_pending'] = True
        result['next'] = "buchhaltung veroeffentlichen status, danach buchhaltung veroeffentlichen resume; Buchung nicht erneut anlegen."
    return result
