# DATEV-Export

Im Dashboard oben **DATEV-Export** wählen. Der Dialog zeigt vor dem Download das
Jahr, die Zahl der übernommenen Zahlungen/Pauschalen und alle bekannten
Auslassungen. Die übrigen Dashboardfilter begrenzen diesen Jahresexport nicht.
Aktuell ist das Kontenprofil für **2026** geprüft; andere Jahre benötigen ein
eigenes geprüftes Profil.

Für den DATEV-Dateikopf die **echte Berater- und Mandantennummer des Empfängers**
eingeben. Diese Werte kommen von der empfangenden Kanzlei beziehungsweise dem
DATEV-Bestand. Das Tool erfindet keine Platzhalter und speichert die Eingaben
nicht dauerhaft. Ohne diese Angaben kann die Exportübersicht bereits als JSON
heruntergeladen werden; eine gültige DATEV-Zieldatei braucht die Nummern.

**DATEV-ZIP herunterladen** erzeugt lokal:

- `EXTF_Buchungsstapel_2026.csv`: erfasste Zahlungen, Teilzahlungen und tatsächliche Erstattungen.
- `EXTF_Pauschalen_2026.csv`: vorhandene bestätigte Homeoffice-Jahrespauschale, gesondert von Geldbewegungen. Entfällt ohne Pauschale.
- `exportbericht.json`: jede Exportzeile mit stabiler anonymer Archivreferenz, Herkunft, Kontenzuordnung, Summen und ausdrücklich ausgeschlossenen Vorgängen.
- `LESEN.txt` und `pruefsummen.json`: Umfang, Importhinweise und SHA-256 der enthaltenen Nutzdateien.

Downloads außerhalb der Repositories speichern. Das Paket enthält keine Namen,
Anschriften, Artikeltexte oder Originalbelege. Lieferantennummern, die nicht reine
Ziffern sind, werden durch stabile Archivkennungen ersetzt; die vollständige
Zuordnung bleibt im verschlüsselten Archiv. Für Originale und sämtliche
Metadatenhistorien den vollständigen Archiv-/Jahresbericht separat bereitstellen.

Alternativ, identisches DATEV-CSV-Format per CLI:

```powershell
buchhaltung datev --year 2026 --advisor ECHTE_BERATERNUMMER --client ECHTE_MANDANTENNUMMER --output NEUER_ORDNER_AUSSERHALB
```

Beide Wege lesen nur. Keine Buchung, Veröffentlichung, Übermittlung an DATEV,
Git-Commits oder neue Bitcoin-Nachweise entstehen. Die CSV-Dateien entsprechen
dem EXTF-Header 700, Kategorie 21, Buchungsstapel-Version 13, mit 125 Nutzfeldern,
Windows-1252, Semikolon, Textquotierung, Dezimalkomma und CR/LF. Import ist für
DATEV Rechnungswesen/Stapelverarbeitung vorgesehen, nicht als behaupteter direkter
Zeilensummenimport in DATEV EÜR Steuern. Die Importoption fordert keine automatische
Festschreibung an. Der Empfängerbestand muss SKR03/EÜR mit den passenden
Kontenfunktionen verwenden.

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

Python und Browser erzeugen bytegleiches DATEV-CSV. Synthetische Tests decken
Vorzeichen, Teilzahlungen, Erstattungen, Pauschalen, Auslassungen, Zielkennungen,
Zeichenkodierung, Feldanzahl, Datumswerte und ZIP-/SHA-256-Integrität ab. Ein
separater Parser prüft die erzeugten Felder gegen das unterstützte Formatprofil.
Das ist kein DATEV-Softwaretest oder Zertifikat. Ein echter Importlauf in einer
DATEV-Anwendung ist mangels Empfängerinstallation nicht erfolgt; der lokale
Prüfer wird nicht als offizielles DATEV-Prüfprogramm ausgegeben.

Quellenstand 21.10.2026:

- [DATEV-Header](https://developer.datev.de/de/file-format/details/datev-format/format-description/header), [Buchungsstapel](https://developer.datev.de/de/file-format/details/datev-format/format-description/booking-batch), [Dateiaufbau/Muster](https://developer.datev.de/de/file-format/details/datev-format/format-description/sample-data).
- [DATEV SKR03 für EÜR, Stand Januar 2026](https://www.datev.de/web/de/shop/produkt-details/kontenrahmen-skr-03-4-absatz-3-estg-11079), [SKR03 2026 mit Erlösen, Aufwendungen und Verrechnungskonto](https://www.datev.de/dnlexom/v2/content/files/st63581358731_de.pdf).
- [Import/Export-Kanäle](https://developer.datev.de/de/file-format/details/datev-format/importexport), [DATEV zu Validierungsgrenzen](https://developer.datev.de/de/product-detail/accounting-extf-files/2.0/documentation/interface-requirements-file).
