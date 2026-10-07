# Lokale Buchhaltung

Ein Werkzeug für eine eigene verschlüsselte Buchhaltungsablage, lokale Rechnungsentwürfe, Belegimport, EÜR-Arbeitsübersicht und Git-/OpenTimestamps-Nachweise. Kleinunternehmerfälle sowie ausdrücklich geprüfte inländische 7-/19-%-Positionen werden unterstützt. Sondersteuerfälle und eine abgabefertige Steuererklärung sind nicht vollständig abgebildet.

Der aktuelle Umfang sind **einzelne EÜR-Einträge**, vor allem Verkäufe und zugehörige Ausgaben wie Porto und Marktplatzgebühren. Vine-Entnahmen und eine vollständige EÜR folgen erst in späteren Schritten. Die [Verfahrensdokumentation](docs/verfahrensdokumentation.md) beschreibt technische Kontrollen, organisatorische Pflichten und offene Punkte. Vor dem betrieblichen Einsatz die [betriebliche Ergänzung](docs/betriebliche-ergaenzung-vorlage.md) privat ausfüllen; diese Vorlage ist kein Konformitätsnachweis.

## Originale, E-Rechnungen und Aufbewahrung

`buchhaltung beleg inspect PFAD` liest auch eigenständige UBL-/CII-Rechnungs-XML und Rechnungs-XML aus PDF-Anhängen. Gültige strukturierte Daten werden nach lokaler XSD-/EN16931-Prüfung in der Metadatenvorlage vorbefüllt; Zahlung, Kategorie und betrieblicher Bezug bleiben zu bestätigen. Ein PDF ohne Rechnungs-XML bleibt ein PDF-Original. Eine nachträglich erzeugte XML ersetzt niemals das empfangene Original.

Ein freigegebener lokaler Rechnungsabschluss erzeugt PDF **und eigenständige EN16931-UBL-2.1-XML** aus denselben Daten sowie einen Validierungsnachweis. Finanzielle Stornos/Teilerstattungen erhalten ebenfalls XML mit Originalbezug. Formale Berichtigungen bleiben derzeit verknüpfte PDF-Dokumente. `buchhaltung rechnung preview ID --output NEUER_ORDNER_AUSSERHALB --e-invoice` exportiert die XML zur Prüfung; Test-XML trägt eine Testnummer und reserviert keine endgültige Rechnungsnummer. Das ist keine XRechnung-CIUS-Implementierung und kein als ZUGFeRD zertifiziertes PDF/A-3. Kein Versand erfolgt automatisch.

Alle Originale, XML, Metadatenhistorien, Entwürfe, Zahlungen, Prüfergebnisse und archivierten Zusatznachweise bleiben erhalten. Die interne Mindestaufbewahrung beträgt **elf volle Kalenderjahre** ab Jahresende des letzten relevanten Vorgangs zum Dokument. `buchhaltung archiv retention` zeigt die frühestmögliche Prüfung; es gibt keinen automatischen Löschlauf. Laufende Verfahren oder andere Aufbewahrungsgründe können die Frist verlängern. Auch Git-Historie und Sicherungen müssen bei einem späteren Löschkonzept berücksichtigt werden.

`buchhaltung archiv export --output NEUER_ORDNER_AUSSERHALB` exportiert stets den vollständigen aktuellen Archivbestand einschließlich aller im Katalog enthaltenen Historien. `--year` ist nur eine Ansichtsangabe und lässt keine Archivdaten weg. `catalog.json` enthält die vollständigen Metadaten, `export-manifest.json` die Original-Zuordnung; `database.json`/`index.html` bieten die Belegansicht. CD-Exporte enthalten zusätzlich beide vollständigen Git-Historien samt verschlüsselter Migrationshistorie. Passwort und `.env` gehören in keine Sicherung oder Klartextansicht.

Abrechnungen, Banknachweise oder zunächst ungeklärte Belege ohne Ausgabenbuchung ablegen:

```powershell
.venv\Scripts\buchhaltung.exe archiv evidence --file 'ORIGINAL_AUSSERHALB' --metadata 'NACHWEIS_JSON_AUSSERHALB'
```

Die Nachweismetadaten enthalten genau `date` (ISO-Datum), `description` und `verification_basis`. Dieser Archivvorgang führt die Commit-/Push-/OTS-Pipeline aus, erzeugt aber keinen EÜR-Eintrag und keinen Zahlungsfluss. Monatliche CD-Sicherung und Rückleseprüfung bleiben getrennte Arbeitsschritte.

## Verkaufsabgleich, Lieferanten-Erstattungen und Sicherungsregister

`buchhaltung abgleich ebay --days 90 --save` liest alle API-Seiten des gewählten Fensters, prüft SRN/Order-Aliasse und vergleicht Rechnungsbetrag und Originalbestand. Ergebnisse und empfangene API-Antworten werden verschlüsselt samt Zeitfenster gespeichert und durch die private Commit-/Push-/OTS-Pipeline veröffentlicht. Ohne `--save` ist der Aufruf nur lesend. `buchhaltung abgleich status` zeigt den letzten gespeicherten Abruf. Für einen täglichen Lauf den Speicherbefehl in den bestehenden Scheduler aufnehmen; das Tool selbst läuft nicht ständig im Hintergrund. Kein automatischer eBay-Abrechnungs-, Gebühren- oder Auszahlungsimport, keine automatische Rechnungserstellung und keine Bankabstimmung. Fehlende oder lediglich extern referenzierte Belege bleiben sichtbar.

Lieferanten-Stornos und Minderungen über `buchhaltung beleg inspect PFAD` einlesen. In den geprüften Metadaten `document_type: "supplier_credit"`, `original_id` der vorhandenen Ausgabe und `correction_reason` ergänzen. Brutto/Netto/Steuer als positive Nennbeträge angeben. Der normale `prepare`-/`book --revision ... --approved`-Ablauf speichert den verknüpften Minderungsbeleg mit negativen Beträgen; die Originalausgabe und deren Nummer bleiben erhalten. Bei strukturiertem XML wird die Belegart erkannt. Eine tatsächliche Erstattung separat mit positivem Betrag und Nachweis über `zahlung erfassen` zuordnen oder beim bestätigten Eingang `pay_date`, `paid_amount` und `payment_evidence` angeben. Nur der tatsächliche Geldzufluss mindert die Zahlungs-Ausgaben. Keine eigene Rechnungsnummer wird verbraucht und keine Bankzahlung ausgeführt.

```powershell
.venv\Scripts\buchhaltung.exe sicherung export --output 'NEUER_ORDNER_AUSSERHALB'
.venv\Scripts\buchhaltung.exe sicherung status
.venv\Scripts\buchhaltung.exe sicherung bestaetigen --id 'BACKUP_ID_AUS_EXPORT' --directory 'PFAD_ZUM_MEDIUM' --medium 'MEDIENKENNUNG' --written --approved
.venv\Scripts\buchhaltung.exe sicherung test --id 'BACKUP_ID_AUS_EXPORT' --directory 'PFAD_ZUM_MEDIUM'
```

Der Export registriert nur einen vorbereiteten Snapshot. Das Medium erst nach tatsächlichem Schreiben und Abschließen bestätigen; die Bestätigung liest sämtliche Paketdateien vom angegebenen Medium und vergleicht den registrierten Manifesthash. Der Exportordner selbst ist dafür kein zulässiges Rückleseziel. Es gibt keine automatische Brennererkennung. `sicherung test` stellt beide Git-Bundles isoliert außerhalb der Repos wieder her, prüft Git-Objekte, Archiv/Originale und historische Gitnachweise und erhält das Ergebnis im verschlüsselten Register. Neuinstallation der Abhängigkeiten und erneute Bitcoin-Verifikation sind gesonderte Tests. Ein fertiger, noch nicht registrierter Export lässt sich mit `sicherung registrieren ORDNER` eintragen.

Das Offline-Dashboard zeigt den letzten API-Abgleich, monatlichen Sicherungsbedarf, Registerstände und Bitcoin-Nachweisstatus. Es zeigt passende Befehle; API-/Medienaktionen führt es nicht aus. `veroeffentlichen confirm` erhält erfolgreiche Bitcoin-Prüfungen in einem an genaue Datei-Hashes gebundenen privaten Cache und aktualisiert das Dashboard. Öffentliche Verfahrensbeschreibung und private Betriebsangaben werden bei jeder Funktionsänderung mitgepflegt. Offene betriebliche Zuständigkeiten bleiben offen.

## Technische Protokolle und Prüfexport

Katalogänderungen werden automatisch in einem verschlüsselten, verketteten Änderungsprotokoll gespeichert. Vorherige Werte, Änderungszeitpunkt und Toolrevision bleiben prüfbar. Vorhandene Originaldateien und ihre Inventar-Prüfsummen dürfen die Helfer nicht überschreiben oder entfernen. Die Veröffentlichung speichert außerdem die tatsächlich bestandene technische Archivprüfung. Das belegt keinen vollständigen Quellenabgleich.

Der vollständige Prüfexport enthält zusätzlich `catalog-nodes.csv` (sämtliche Katalogwerte und Verknüpfungen), `records.csv` (Belege/Entwürfe einschließlich Versionen), `documents.csv`, `record-documents.csv` und `data-description.json` mit Feldtypen, Format und Prüfsummen. Alle Dateien entstehen außerhalb beider Repos; die normalen Arbeitsbefehle bleiben gleich. Bestehende Archive ohne dieses Protokoll bleiben lesbar und starten es erst bei der nächsten Katalogänderung mit einem ausdrücklich bezeichneten Ausgangsstand. Frühere Ereigniszeiten werden nicht erfunden.

## Zwei unabhängige Repositories

Dieses öffentliche Repository enthält ausschließlich Code, Vorlagen, Skills und synthetische Tests. `daten/` ist vollständig ignoriert: dort wird ein **eigenständiges privates Git-Repo** geklont. Es gibt keine Submodule-Verknüpfung. Belege, Schlüsselhülle, verschlüsselte Datenbank, verschlüsselte Checkliste, Nachweise und das persönliche Dashboard gehören ausschließlich ins Datenrepo. `.env` bleibt lokal.

## Einrichtung

Python 3.11+ und Git installieren. Ein leeres privates Datenrepo bei GitHub anlegen und das Tool klonen. Im Toolordner:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
.venv\Scripts\python.exe -X utf8 scripts\setup_workspace.py --data-url 'git@github.com:DEIN_KONTO/DEIN_PRIVATES_DATENREPO.git'
```

In `daten/.env` lokal `ENCRYPTION_PASSWORD` hinterlegen. Optional benötigte eBay-, GMX- und Vine-Zugangswerte ebenfalls dort konfigurieren; nichts davon committen. Git-Autor im privaten Repo konfigurieren. Vor dem ersten Archiv-CLI muss dort ein initialer Commit mit Rollenmarkierung und Konfiguration existieren und nach `origin/main` gepusht sein:

```powershell
git -C daten add .bookkeeping-data.json .gitignore .gitattributes workspace.json AGENTS.md verfahrensdokumentation.md buchhaltung
git -C daten commit -m "Initialize private bookkeeping workspace"
git -C daten push -u origin main
.venv\Scripts\python.exe -X utf8 scripts\bookkeeping_archive.py init
```

`init` erzeugt eine leere verschlüsselte Ablage samt vollständiger Veröffentlichung. Vorhandene Daten nicht neu initialisieren oder Schlüssel ersetzen. Auch dieses Toolrepo muss einen sauberen eingecheckten Stand besitzen; bei einem normalen Klon ist das bereits der Fall.

## Bedienung

`buchhaltung` ist der gemeinsame lokale Einstieg. Nach Installation steht der Befehl in `.venv/Scripts/`; alternativ funktioniert `.venv\Scripts\python.exe -X utf8 -m autobookkeeping.cli`. Die vorhandenen Helferskripte bleiben für Automatisierung und Wiederaufnahme verfügbar.

```powershell
.venv\Scripts\buchhaltung.exe --help
.venv\Scripts\buchhaltung.exe rechnung list
.venv\Scripts\buchhaltung.exe beleg inspect 'PFAD_ZUM_BELEG'
.venv\Scripts\buchhaltung.exe zahlung erfassen --metadata 'GEPRUEFTE_ZAHLUNG.json' --approved
.venv\Scripts\buchhaltung.exe pruefen
.venv\Scripts\buchhaltung.exe dashboard
.venv\Scripts\buchhaltung.exe sicherung export --output 'NEUER_ORDNER_AUSSERHALB'
.venv\Scripts\buchhaltung.exe veroeffentlichen status
```

Dieser Toolstand enthält keine Anbindung an einen externen Rechnungsdienst. Historische Quellkennungen bleiben unverändert in der privaten verschlüsselten Ablage; vorhandene Positionen und Zahlungen werden lokal ausgewertet. Exporte aus alten Diensten vorbereiten und prüfen, bevor sie als lokale Originalbelege importiert werden. Ein Import stellt keine neue Rechnung aus.

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

## Lokales Rechnungsprofil und Nummernübergabe

Ein neuer Workspace erhält sein Absenderprofil mit `buchhaltung rechnung configure --profile PROFIL_JSON_AUSSERHALB --last-number 0000`. Die Profildatei enthält `name`, `street`, `postal_code`, `city`, `country_iso`, `tax_number`, `small_business`, `tax_note` und `introduction`. Das vorhandene Profil nicht neu initialisieren. Der geprüfte Nummernstand muss mit dem Archiv übereinstimmen; bei einem neuen leeren Bestand ist er `0000`.

Die Aktivierung liest einen zuvor geprüften lokalen Übergabebericht außerhalb beider Repos. Er enthält `version: 1`, `last_number` als numerischen Text, `inventory_complete: true`, `unfinalized: 0`, `external_numbering_stopped: true` und eine konkrete `verification_basis`. Diese Angaben sind ausdrücklich zu prüfen; ein Bericht beweist nicht selbst die Vollständigkeit eines früheren Dienstes. Erst nach gesonderter Freigabe:

```powershell
.venv\Scripts\buchhaltung.exe rechnung activate --last-number GEPRUEFTE_NUMMER --handover 'UEBERGABEBERICHT_AUSSERHALB.json' --approved
```

Der Bericht wird mit Prüfbasis und SHA256 verschlüsselt als Übergabenachweis gespeichert. Vorbereitung, lokale Dublettenprüfung und Aktivierung benötigen keinen Zugriff auf einen früheren Rechnungsdienst. eBay/DHL/Vine-Abfragen für den eBay-Ablauf bleiben erhalten; sie senden keine Rechnung. Aktivierung und das Abschließen eines konkreten Entwurfs bleiben getrennte Freigaben.

Schreibende Haupt-CLIs prüfen zuerst Datenrolle, exakte Git-Wurzel, privaten Remote und eine saubere veröffentlichte Toolversion. Danach laufen Archivprüfung, Dashboard, Datencommit/Push und ein separater OTS-Commit/Push im privaten Repo. Dessen `tool-version.json` hält den verwendeten Code-Commit fest. Ein OTS-Kalendernachweis ist zunächst ausstehend; `confirm` holt spätere Bitcoin-Bestätigungen nach und veröffentlicht geänderte Nachweise. Keine Geldbewegung oder E-Mail wird dadurch ausgeführt.

## Sicherheit und Updates

Die Einrichtung installiert Hooks: normale Commits/Pushes im Toolcheckout werden blockiert; der Datenhook prüft den Git-Index und erzeugt das Dashboard. Hooks sind Schutz gegen Versehen, keine absolute Berechtigungssperre. Die Buchhaltungs-CLIs prüfen das Ziel unabhängig davon; ein fehlendes `daten/.git` blockiert sie.

Toolupdates erfolgen mit `git pull --ff-only` und anschließender Aktualisierung der Python-Abhängigkeiten. Offene Veröffentlichungen zuerst mit ihrer bisherigen Toolversion abschließen. Für bewusste Toolentwicklung lokal `git config bookkeeping.allowToolCommit true` setzen und danach wieder `false`. Das öffentliche Toolrepo enthält niemals die private Repo-Adresse.

Öffentliche Maintainer-Commits benötigen einen bewusst gewählten öffentlichen Anzeigenamen und eine GitHub-Noreply-Adresse. `user.name`/`user.email` und `bookkeeping.publicName`/`bookkeeping.publicEmail` im lokalen Git-Config entsprechend setzen. Die Hooks prüfen den Index vor dem Commit sowie alle erreichbaren Commit-Versionen und die tatsächlich gepushten Referenzen vor dem Push. Belege, Datenbanken, Dashboard und Zeitnachweise dürfen ausschließlich ins private Datenrepo. Wenn die lokale Datenablage verfügbar ist, prüft `scripts/audit_public_repo.py` zusätzlich bekannte private Namen, Kennungen und Zugangswerte im Speicher. Prüfergebnisse enthalten keine gefundenen privaten Werte. Künstliche Testbeispiele verwenden erfundene Personen, Kennungen und Daten; echte Kundendaten gehören auch nicht in Tests.

Der öffentliche Maintainer-Alias lautet `hutauf`. Die zwei bereits veröffentlichten Codecommits mit dem früheren Alias bleiben unverändert, damit bestehende Versionsverweise gültig bleiben. `.github/public-identities.toml` erlaubt die frühere Identität ausschließlich für diese beiden vollständigen Commit-Hashes; neue Commits müssen die aktuell konfigurierte Identität verwenden. Inhalt und Datenschutz werden auch für diese historischen Commits vollständig geprüft.

Die CD-Sicherung enthält die öffentliche Toolhistorie als Bundle und die private Datenhistorie als zusätzlich verschlüsseltes Bundle. Historische Zeitnachweise aus einer Migration bleiben mit einem verschlüsselten Legacy-Bundle prüfbar. Brennen und Rücklesen erfolgen separat. Passwort unabhängig sichern; weder Timestamp noch Verschlüsselung allein bestätigen vollständige GoBD-/DSGVO-Konformität.

## Entwicklung

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Eigener Toolcode: MIT, siehe `LICENSE`. Die unveränderten CEN-EN16931-Validierungsartefakte stehen unter EUPL 1.2; Herkunft, Version und Prüfsummen liegen in `src/autobookkeeping/validation/`.
