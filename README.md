# Lokale Buchhaltung

Ein Werkzeug für eine eigene verschlüsselte Buchhaltungsablage, lokale Rechnungsentwürfe, Belegimport, EÜR-Arbeitsübersicht und Git-/OpenTimestamps-Nachweise. Kleinunternehmerfälle sowie ausdrücklich geprüfte inländische 7-/19-%-Positionen werden unterstützt. Sondersteuerfälle und eine abgabefertige Steuererklärung sind nicht vollständig abgebildet.

## Zwei unabhängige Repositories

Dieses öffentliche Repository enthält ausschließlich Code, Vorlagen, Skills und synthetische Tests. `daten/` ist vollständig ignoriert: dort wird ein **eigenständiges privates Git-Repo** geklont. Es gibt keine Submodule-Verknüpfung. Belege, Schlüsselhülle, verschlüsselte Datenbank, verschlüsselte Checkliste, Nachweise und das persönliche Dashboard gehören ausschließlich ins Datenrepo. `.env` bleibt lokal.

## Einrichtung

Python 3.11+ und Git installieren. Ein leeres privates Datenrepo bei GitHub anlegen und das Tool klonen. Im Toolordner:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
.venv\Scripts\python.exe -X utf8 scripts\setup_workspace.py --data-url 'git@github.com:DEIN_KONTO/DEIN_PRIVATES_DATENREPO.git'
```

In `daten/.env` lokal `ENCRYPTION_PASSWORD` hinterlegen. Optional benötigte eBay-, Invoiz-, GMX- und Vine-Zugangswerte ebenfalls dort konfigurieren; nichts davon committen. Git-Autor im privaten Repo konfigurieren. Vor dem ersten Archiv-CLI muss dort ein initialer Commit mit Rollenmarkierung und Konfiguration existieren und nach `origin/main` gepusht sein:

```powershell
git -C daten add .bookkeeping-data.json .gitignore .gitattributes workspace.json AGENTS.md buchhaltung
git -C daten commit -m "Initialize private bookkeeping workspace"
git -C daten push -u origin main
.venv\Scripts\python.exe -X utf8 scripts\bookkeeping_archive.py init
```

`init` erzeugt eine leere verschlüsselte Ablage samt vollständiger Veröffentlichung. Vorhandene Daten nicht neu initialisieren oder Schlüssel ersetzen. Auch dieses Toolrepo muss einen sauberen eingecheckten Stand besitzen; bei einem normalen Klon ist das bereits der Fall.

## Bedienung

Alle Befehle im **äußeren Toolordner** ausführen:

```powershell
.venv\Scripts\python.exe -X utf8 scripts\bookkeeping_archive.py verify
.venv\Scripts\python.exe -X utf8 scripts\bookkeeping_archive.py report
.venv\Scripts\python.exe -X utf8 scripts\build_bookkeeping_dashboard.py
.venv\Scripts\python.exe -X utf8 scripts\homeoffice.py preview --year 2026
.venv\Scripts\python.exe -X utf8 scripts\receipt.py inspect 'PFAD_ZUM_BELEG'
.venv\Scripts\python.exe -X utf8 scripts\publish_bookkeeping.py status
.venv\Scripts\python.exe -X utf8 scripts\publish_bookkeeping.py resume
.venv\Scripts\python.exe -X utf8 scripts\publish_bookkeeping.py confirm
```

`daten/dashboard.html` per Doppelklick öffnen. Die statische Seite zeigt für Änderungen passende CLI-Befehle. Homeoffice hat 210 Tage als Eingabevorgabe, keinen automatisch gebuchten Jahresansatz. Belege und Metadaten vor einer konkreten Buchungsfreigabe prüfen. Lokale Rechnungen starten im Probebetrieb; der Produktivwechsel und die fortlaufende Nummernübernahme verlangen eine gesonderte Freigabe.

Schreibende Haupt-CLIs prüfen zuerst Datenrolle, exakte Git-Wurzel, privaten Remote und eine saubere veröffentlichte Toolversion. Danach laufen Archivprüfung, Dashboard, Datencommit/Push und ein separater OTS-Commit/Push im privaten Repo. Dessen `tool-version.json` hält den verwendeten Code-Commit fest. Ein OTS-Kalendernachweis ist zunächst ausstehend; `confirm` holt spätere Bitcoin-Bestätigungen nach und veröffentlicht geänderte Nachweise. Keine Geldbewegung oder E-Mail wird dadurch ausgeführt.

## Sicherheit und Updates

Die Einrichtung installiert Hooks: normale Commits/Pushes im Toolcheckout werden blockiert; der Datenhook prüft den Git-Index und erzeugt das Dashboard. Hooks sind Schutz gegen Versehen, keine absolute Berechtigungssperre. Die Buchhaltungs-CLIs prüfen das Ziel unabhängig davon; ein fehlendes `daten/.git` blockiert sie.

Toolupdates erfolgen mit `git pull --ff-only` und anschließender Aktualisierung der Python-Abhängigkeiten. Offene Veröffentlichungen zuerst mit ihrer bisherigen Toolversion abschließen. Für bewusste Toolentwicklung lokal `git config bookkeeping.allowToolCommit true` setzen und danach wieder `false`. Das öffentliche Toolrepo enthält niemals die private Repo-Adresse.

Öffentliche Maintainer-Commits benötigen einen bewusst gewählten öffentlichen Anzeigenamen und eine GitHub-Noreply-Adresse. `user.name`/`user.email` und `bookkeeping.publicName`/`bookkeeping.publicEmail` im lokalen Git-Config entsprechend setzen. Die Hooks prüfen den Index vor dem Commit sowie alle erreichbaren Commit-Versionen und die tatsächlich gepushten Referenzen vor dem Push. Belege, Datenbanken, Dashboard und Zeitnachweise dürfen ausschließlich ins private Datenrepo. Wenn die lokale Datenablage verfügbar ist, prüft `scripts/audit_public_repo.py` zusätzlich bekannte private Namen, Kennungen und Zugangswerte im Speicher. Prüfergebnisse enthalten keine gefundenen privaten Werte. Künstliche Testbeispiele verwenden erfundene Personen, Kennungen und Daten; echte Kundendaten gehören auch nicht in Tests.

Die CD-Sicherung enthält die öffentliche Toolhistorie als Bundle und die private Datenhistorie als zusätzlich verschlüsseltes Bundle. Historische Zeitnachweise aus einer Migration bleiben mit einem verschlüsselten Legacy-Bundle prüfbar. Brennen und Rücklesen erfolgen separat. Passwort unabhängig sichern; weder Timestamp noch Verschlüsselung allein bestätigen vollständige GoBD-/DSGVO-Konformität.

## Entwicklung

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Lizenz: MIT, siehe `LICENSE`.
