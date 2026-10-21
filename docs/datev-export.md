# DATEV-Export

Der Export läuft ausschließlich lokal über die CLI. Im Dashboard oben
**DATEV-Export** öffnen, das Jahr, die echten Zielnummern und einen neuen
Exportordner außerhalb beider Repositories angeben. **Befehl kopieren**, im
Toolordner in PowerShell einfügen und ausführen. Der Dialog erzeugt keine Dateien
und zeigt nur eine anonymisierte Vorschau zum gespeicherten Dashboardstand.

```powershell
buchhaltung datev --year 2026 --advisor ECHTE_BERATERNUMMER --client ECHTE_MANDANTENNUMMER --output NEUER_ORDNER_AUSSERHALB
```

Berater- und Mandantennummer kommen von der empfangenden Kanzlei beziehungsweise
dem DATEV-Bestand. Sie bestimmen den Zielbestand im DATEV-Dateikopf; das Tool
erfindet keine Nummern. Das Archiv wird mit dem lokal konfigurierten
`ENCRYPTION_PASSWORD` entschlüsselt. Das Passwort gehört weder in den Befehl noch
in den Export. Fehlt die Konfiguration oder stimmt sie nicht, schlägt der Export
fehl. Es gibt keine separate Anmeldung bei DATEV und keinen Versand.

Der neue Zielordner enthält:

- `EXTF_Buchungsstapel_2026.csv`: erfasste Zahlungen, Teilzahlungen und tatsächliche Erstattungen, mit vorhandenen Kunden-/Lieferantennamen.
- `EXTF_Pauschalen_2026.csv`: vorhandene bestätigte Homeoffice-Jahrespauschale, separat von Geldbewegungen. Entfällt ohne Pauschale.
- `exportbericht.json`: jede Exportzeile und Auslassung mit Archivbezug, Original-Belegnummer, vorhandenen Geschäftspartnerdaten, Herkunft, Kontenzuordnung und Summen.
- `archiv/`: vollständiger Archivexport **aller Jahre**, einschließlich Original-PDF/XML, vollständigem UTF-8-Katalog, Personen-/Quellmetadaten, Historien, Tabellen und vorhandenen Nachweisen. Der DATEV-Jahresfilter entfernt keine Archivdaten. Bereits im Archiv fehlende Originale werden dadurch nicht ergänzt.
- `LESEN.txt` und `pruefsummen.json`: Umfang, Importhinweise und SHA-256 sämtlicher Nutzdateien einschließlich des Begleitarchivs.

**Der Export enthält personenbezogenen Klartext.** Geschützt aufbewahren und
nur gezielt weitergeben; niemals ins Tool- oder Datenrepo zurückkopieren.
Es entsteht ein Ordner, keine ZIP-Datei. Ein unterbrochener Export hinterlässt
keinen scheinbar fertigen Zielordner. Der vollständige Begleitbestand ist eine
separate Bereitstellung für den Empfänger; er wird nicht automatisch von DATEV
als Buchungsstapel oder Dokumentenablage importiert.

Kunden-/Lieferantennamen stehen im Buchungstext (höchstens 60 Zeichen) und in der
Beleginformation „Geschäftspartner“ (höchstens 210 Zeichen). Zulässige vollständige
Belegnummern werden übernommen; andernfalls bleibt ein stabiler Ersatz im
Belegfeld, mit Originalnummer im Bericht und in einer weiteren Beleginformation.
DATEV-Felder benötigen Windows-1252: nicht darstellbare Zeichen werden dort durch
`?` ersetzt; Kürzungen, Leerraumbereinigung und Ersetzungen sind pro Zeile als
`text_adaptations` vermerkt. Im UTF-8-Bericht und vollständigen Archiv bleiben die
unveränderten Daten erhalten. Fehlende Namen werden als `counterparty_missing`
markiert und nicht erfunden. Die Übergabe erzeugt keine Debitoren-/Kreditorenkonten
oder OPOS-Stammdaten; Anschriften und weitere Kundendaten stehen im Begleitarchiv.

Nur Lesezugriff: keine Buchung, Übermittlung an DATEV, Git-Commits oder neuen
Bitcoin-Nachweise. Die CLI prüft den aktuellen Archivbestand und schreibt nur
außerhalb beider Repos in einen neuen Ordner. Die CSV-Dateien verwenden
EXTF-Header 700, Kategorie 21, Buchungsstapel-Version 13, 125 Nutzfelder,
Windows-1252, Semikolon, Textquotierung, Dezimalkomma und CR/LF. Import ist für
DATEV Rechnungswesen/Stapelverarbeitung vorgesehen, kein zugesicherter direkter
Zeilensummenimport in DATEV EÜR Steuern. Die Importoption fordert keine automatische
Festschreibung an. Der Empfängerbestand muss SKR03/EÜR mit passenden Kontenfunktionen
verwenden. Aktuell ist ausschließlich das Kontenprofil für **2026** geprüft.

## Fachliches Exportprofil

Die Anwendung bleibt eine einfache Einnahmen-/Ausgabenaufzeichnung. Nur der
Exportadapter übersetzt Kategorien in das technische DATEV-Format. Er nutzt
Kleinunternehmer-Erlöse 8192, Software/EDV 4806, Porto 4910, Bürobedarf 4930,
Wareneingang ohne Vorsteuerabzug 3349 sowie sonstige Kosten 4900. Marktplatzkosten
und historische Kosten ohne feinere Kategorie stehen auf 4900 und werden im
Begleitbericht als Sammelzuordnung gekennzeichnet; eine feinere Aufteilung ist
dadurch nicht behauptet. Die Pauschale steht auf 4287.
Gegenkonto ist 1371, das nicht ergebniswirksame EÜR-Verrechnungskonto. Es wird
kein tatsächliches Bankkonto oder Bankabgleich erfunden.

Erfasst wird ausschließlich der Geldfluss: Einnahmen und Lieferantenerstattungen
im Haben des jeweiligen Erfolgs-/Aufwandskontos, Auszahlungen und Kundenrückzahlungen
im Soll. Rechnungsbeträge werden nicht zusätzlich zu ihren Zahlungen exportiert.
Die Homeoffice-Jahrespauschale wird zum Jahresende als Jahresabschlussstapel
ausgegeben und verändert keine Zahlungsstatistik. Sie darf im Empfängerbestand
nicht zusätzlich ein zweites Mal angesetzt werden.

Alle Aufwendungen werden brutto ohne Vorsteuerabzug übergeben, Kennzeichen K
(keine Umsatzsteuerrechnung), ohne Umsatzsteuerschlüssel. Nicht bestätigter
Kleinunternehmerstatus, bekannte Auslands-/Sondersteuerfälle, ungeklärte Privatanteile,
fehlende Originale und widersprüchliche Zahlungsquellen werden nicht automatisch
kontiert. Eine bloße eBay-Käuferzahlung ohne zugeordnete tatsächliche
Zahlungsverfügbarkeit wird ebenfalls ausgewiesen. Amazon-Produkttester-Leistungsumsätze
und Reverse Charge gehören weiterhin nicht zum Exportumfang. Ein gebuchter
Minderungsbeleg ohne tatsächliche Erstattung erzeugt keine Geldbewegung.

Der Bericht nennt Auslassungen ausdrücklich; er ist weder eine vollständige
betriebliche EÜR noch eine abgeschlossene Steuererklärung. Bei wiederholtem
Import desselben oder eines überlappenden Exports können Doppelbuchungen entstehen.
Stabile Referenzen erleichtern den Vergleich, sind keine zugesicherte
Dublettensperre der empfangenden Software.

## Prüfung und Quellen

Synthetische CLI- und Dashboardtests decken
Vorzeichen, Teilzahlungen, Erstattungen, Pauschalen, Auslassungen, Zielkennungen,
Zeichenkodierung, Feldanzahl, Datumswerte und SHA-256 sämtlicher Exportdateien ab. Ein
separater Parser prüft die erzeugten Felder gegen das unterstützte Formatprofil.
Das ist kein DATEV-Softwaretest oder Zertifikat. Ein echter Importlauf in einer
DATEV-Anwendung ist mangels Empfängerinstallation nicht erfolgt; der lokale
Prüfer wird nicht als offizielles DATEV-Prüfprogramm ausgegeben.

Quellenstand 21.10.2026:

- [DATEV-Header](https://developer.datev.de/de/file-format/details/datev-format/format-description/header), [Buchungsstapel](https://developer.datev.de/de/file-format/details/datev-format/format-description/booking-batch), [Dateiaufbau/Muster](https://developer.datev.de/de/file-format/details/datev-format/format-description/sample-data).
- [DATEV SKR03 für EÜR, Stand Januar 2026](https://www.datev.de/web/de/shop/produkt-details/kontenrahmen-skr-03-4-absatz-3-estg-11079), [SKR03 2026 mit Erlösen, Aufwendungen und Verrechnungskonto](https://www.datev.de/dnlexom/v2/content/files/st63581358731_de.pdf).
- [Import/Export-Kanäle](https://developer.datev.de/de/file-format/details/datev-format/importexport), [DATEV zu Validierungsgrenzen](https://developer.datev.de/de/product-detail/accounting-extf-files/2.0/documentation/interface-requirements-file).
