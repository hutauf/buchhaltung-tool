# Lokale Buchhaltung

eBay-Verkäufe und zugehörige Belege lokal verwalten: Rechnungen vorbereiten, Originale verschlüsselt archivieren und den Bestand im Dashboard überblicken. Aktuell eine **Betaversion für einzelne EÜR-Einträge**.

## Zum Laufen bringen

Du brauchst Python 3.11+, Git, einen GitHub-Zugang und ein **leeres privates Datenrepo**. Der GitHub-Zugang muss dessen Privatheit prüfen und dorthin pushen können; [Zugang einrichten](docs/einrichtung.md#github-zugang). Unter Windows einen kurzen Installationspfad verwenden.

**1. Tool installieren** — PowerShell öffnen, `DEIN-KONTO/DEIN-DATENREPO` ersetzen:

```powershell
git clone https://github.com/hutauf/buchhaltung-tool.git C:/bk/tool
cd C:/bk/tool
py -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -X utf8 scripts/setup_workspace.py --data-url 'https://github.com/DEIN-KONTO/DEIN-DATENREPO.git'
```

**2. Passwort hinterlegen:** `daten/.env` anlegen und `ENCRYPTION_PASSWORD='DEIN-STARKES-PASSWORT'` eintragen. Passwort getrennt sichern. Belege gehören ins private Datenrepo; Zugangsdaten bleiben lokal.

**3. Leeres Archiv starten** — Git-Name und E-Mail müssen eingerichtet sein ([Anleitung](docs/einrichtung.md#git-autor)):

```powershell
git -C daten add .bookkeeping-data.json .gitignore .gitattributes workspace.json AGENTS.md verfahrensdokumentation.md buchhaltung
git -C daten commit -m "Initialize private bookkeeping workspace"
git -C daten push -u origin main
.venv/Scripts/buchhaltung.exe archiv init
```

Diese Schritte gelten für eine Neueinrichtung. Bei vorhandenem Bestand nach der [Einrichtungsanleitung](docs/einrichtung.md) vorgehen. Für eigene Rechnungen anschließend das [Absenderprofil einrichten](docs/einrichtung.md#rechnungsprofil).

## eBay und GMX/DHL anbinden

In `daten/.env` die eBay-Zugangsdaten und den GMX-Login ergänzen: [Schritt für Schritt](docs/einrichtung.md#ebay-und-gmxdhl). Damit lassen sich Verkäufe aus eBay abrufen und passende DHL-Belege aus den Bestätigungsmails suchen und herunterladen. Ein eigener DHL-API-Zugang ist dafür nicht nötig.

```powershell
.venv/Scripts/buchhaltung.exe ebay --days 30 --limit 10 --paid-only
.venv/Scripts/python.exe -X utf8 scripts/find_dhl_receipt.py 'SENDUNGSNUMMER_ODER_SUCHBEGRIFF' --download --output-dir C:/bk/belegpruefung/dhl
```

Einrichtung und Abruf buchen noch keine Rechnung oder Ausgabe. Rechnungsentwürfe brauchen derzeit zusätzlich eine [Vine-Anbindung](docs/einrichtung.md#vine). Regelmäßige Abrufe müssen im Scheduler eingerichtet werden.

## Im Alltag

```powershell
.venv/Scripts/buchhaltung.exe --help
.venv/Scripts/buchhaltung.exe beleg inspect 'PFAD_ZUM_BELEG'
.venv/Scripts/buchhaltung.exe dashboard
```

`daten/dashboard.html` per Doppelklick öffnen. Die Seite zeigt den Bestand und die passenden kopierbaren Befehle für Änderungen. Rechnungsabschlüsse, Ausgaben und Zahlungen verlangen eine konkrete Freigabe. Vor dem ersten produktiven Rechnungsabschluss ist die geprüfte Nummernübernahme erforderlich. Die vollständigen Abläufe stehen im [Handbuch](docs/handbuch.md).

## Warum diesem Werkzeug vertrauen?

Die [GoBD-Verfahrensdokumentation](docs/verfahrensdokumentation.md) erklärt die Kontrollen und ihre Grenzen. Die wichtigsten Anforderungen:

| Anforderung | Umsetzung und Einschränkung |
|---|---|
| Nachvollziehbarkeit und Ordnung | Originale, Metadaten und Korrekturen bleiben verknüpft; Änderungen werden protokolliert. |
| Unveränderbarkeit | Originale werden nicht überschrieben; Git-Historie und bestätigte Bitcoin-Zeitnachweise machen Änderungen prüfbar. Administratoren können Daten trotzdem löschen; unabhängige Sicherungen bleiben erforderlich. |
| Vollständigkeit, Richtigkeit, zeitgerechte Erfassung | Quellen-, Betrags- und Dublettenprüfungen helfen. Vollständigen Eingang, tatsächliche Zahlungen und rechtzeitige Erfassung musst du sicherstellen. |
| Aufbewahrung und Datensicherheit | Verschlüsselte Originale, elfjährige Archivpolitik, keine automatische Löschung. Passwortsicherung, Zugriffsrechte und geprüfte Sicherungsmedien liegen bei dir. |
| Lesbarkeit und Datenzugriff | Originale und Metadaten lassen sich vollständig exportieren. Benötigte Prüferauswertungen sind gesondert abzustimmen. |
| Verfahrensdokumentation | Technische Beschreibung vorhanden; die [betrieblichen Angaben](docs/betriebliche-ergaenzung-vorlage.md) musst du privat ergänzen und aktuell halten. |

Das ist **keine GoBD-Zertifizierung und keine vollständige EÜR**. Sondersteuerfälle sind nur eingeschränkt unterstützt. Git, Verschlüsselung und Zeitstempel allein ersetzen keinen ordnungsgemäßen Betrieb.

[Versionen](CHANGELOG.md) · [Lizenzhinweise](THIRD_PARTY_NOTICES.md)
