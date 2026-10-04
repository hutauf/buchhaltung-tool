# Verschlüsselte Buchhaltungsablage

Dieser Ordner liegt im unabhängigen privaten Datenrepo. Der äußere Toolordner enthält `scripts/`, Python-Umgebung und den Belegimport-Skill. Alle folgenden Befehle dort starten. Datenbank und Originalbelege liegen unter `daten/buchhaltung/`; `.env` unter `daten/.env` bleibt lokal.

```powershell
.venv\Scripts\python.exe -X utf8 scripts\bookkeeping_archive.py verify
.venv\Scripts\python.exe -X utf8 scripts\bookkeeping_archive.py report
.venv\Scripts\python.exe -X utf8 scripts\build_bookkeeping_dashboard.py
```

`daten/dashboard.html` zeigt eine Übersicht ohne personenbezogene Felder. Änderungsaktionen zeigen den passenden CLI-Befehl. Die Homeoffice-Vorgabe von 210 Tagen ist eine Eingabehilfe; nur belegbare und ausdrücklich bestätigte Tage speichern.

## Allgemeine Ausgabenbelege

```powershell
.venv\Scripts\python.exe -X utf8 scripts\receipt.py inspect 'PFAD_ZUM_PDF_ODER_BILD'
.venv\Scripts\python.exe -X utf8 scripts\receipt.py prepare 'PRUEFORDNER/review.json' --metadata 'PRUEFORDNER/metadaten.json'
```

`inspect` liefert einen Prüfpfad außerhalb beider Repos mit Original, Text, Bildern und JSON-Vorlage. Die zurückgegebenen Pfade verwenden. Die Vorlage aus dem Original vervollständigen: Empfänger `payee`, Lieferanten-Belegnummer `number`, Datum `date`, `currency: "EUR"`, Brutto/Netto/Steuer als Dezimaltexte, ausgewiesener Steuersatz, Kategorie und Beschreibung. Kategorien sind `software_subscriptions`, `marketplace_fees`, `postage`, `office`, `goods`, `other`. Betriebliche Nutzung und konkrete Prüfbasis dokumentieren; Auslands-/Sondersteuerfälle gesondert markieren.

`pay_date`, `paid_amount` und `payment_evidence` nur mit einer konkret geprüften Zahlung setzen; Belegdatum allein reicht nicht. `prepare` erzeugt eine verschlüsselte Vormerkung. Erst nach Prüfung und Freigabe der angezeigten konkreten Revision mit `receipt.py book ID --revision SHA256 --approved` buchen. Der Helfer bewegt kein Geld. Bereits gebuchte Originale nicht nochmals importieren.

## Rechnungen, Korrekturen und Nachweise

`local_invoice.py --help` zeigt den Entwurfs-, Vorschau- und Abschlussablauf sowie Berichtigungen, Storno, Teilminderung und getrennte Zahlungsereignisse. Produktivwechsel und konkrete Abschlüsse benötigen Freigaben. Sondersteuerfälle sind nicht vollständig automatisiert.

Schreibende Helfer veröffentlichen nur das private Repo: Archivprüfung, Dashboard, Datencommit/Push und separater Git-/OpenTimestamps-Nachweis. Bei Unterbrechung `publish_bookkeeping.py status` und `resume` verwenden. Später mit `confirm` die Bitcoin-Bestätigung aktualisieren und prüfen. Die eingesetzte Toolversion steht in `tool-version.json`.

```powershell
.venv\Scripts\python.exe -X utf8 scripts\bookkeeping_archive.py export --output 'PFAD_AUSSERHALB_BEIDER_REPOS'
.venv\Scripts\python.exe -X utf8 scripts\bookkeeping_archive.py cd-export --output 'NEUER_CD_EXPORTORDNER'
.venv\Scripts\python.exe -X utf8 scripts\bookkeeping_archive.py cd-verify 'CD_EXPORTORDNER'
```

Exportierte Originale sind sensible Klartextdaten. CD-Exporte enthalten beide Git-Historien; die private Historie ist zusätzlich verschlüsselt. `WIEDERHERSTELLUNG.txt` beschreibt die Wiederherstellung mit `restore_backup.py`. Passwort getrennt sichern. CD manuell brennen, finalisieren und zurücklesen. Eine Arbeitsübersicht ersetzt keine vollständige Steuererklärung oder rechtliche Prüfung.
