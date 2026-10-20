# Vorschlag: Anlage EÜR und DATEV

Recherche vom 20.10.2026. Dies ist ein fachlicher Entwicklungsvorschlag zur
Besprechung, keine aktive Formularzuordnung und kein vorhandener DATEV-Export.
Der bestehende Jahresbericht wertet die tatsächlich erfassten Daten aus und
enthält den vollständigen Original-/JSON-/CSV-Export.

## Amtliches Formular als Ziel

Grundlage für 2026 ist die [amtliche Anlage EÜR 2026 samt Anleitungen,
BMF-Schreiben vom 01.09.2026](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Einkommensteuer/2026-09-01-anlage-EUER-2026.html).
Die Angaben unten wurden am Original-PDF Version 4, insbesondere den ersten drei
Formularseiten, abgeglichen. Das [Formularpaket](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Einkommensteuer/2026-09-01-anlage-EUER-2026.pdf?__blob=publicationFile&v=4)
und die [ELSTER-Anleitung des Vorjahrs](https://www.elster.de/elsterweb/helpGlobal?themaGlobal=help_euer_ufa_77_2025)
verdeutlichen, warum Formularjahr und fachliche Kennung getrennt zu führen sind.
2026 verschieben sich viele Ausgabenzeilen gegenüber 2025 um eine Zeile.

| Vorgang | Erster Vorschlag für 2026 | Vor Übernahme zu klären |
|---|---|---|
| Betrieb und Person | Allgemeine Angaben, Betriebsart, Rechtsform, Einkunftsart, Inhaber, Wirtschaftsjahr und Steuer-/Wirtschafts-ID | Private Stammdaten; kein Bestandteil des anonymisierten Dashboards |
| Vereinnahmte Kleinunternehmer-Verkäufe | Zeile 12, Kennzahl 111, tatsächlicher Gesamtzufluss | Steuerstatus im jeweiligen Leistungszeitraum und weitere Einnahmen; Stornos ohne Rückzahlung nicht pauschal abziehen |
| Regelbesteuerte Verkäufe | Zeile 15, Kennzahl 112, netto; vereinnahmte Umsatzsteuer getrennt Zeile 17, Kennzahl 140 | Teilzahlungen und zugehörige Steueranteile; bestehende Bruttosumme reicht nicht |
| Steuerfreie/nicht steuerbare Einnahmen und Leistungen mit Steuerschuld des Empfängers | Zeile 16, Kennzahl 103 | Diese Fälle ausdrücklich unterscheiden; nicht allein aus einem Steuersatz von null ableiten |
| Software-Abos | Laufende EDV-Kosten, Zeile 51, Kennzahl 228, als Ausgangsvorschlag | Laufender Aufwand versus Anschaffung/Lizenz; betrieblicher Anteil; ausländische Leistung/Reverse Charge separat |
| Briefporto/Büromaterial | Arbeitsmittel, Zeile 52, Kennzahl 229 | Pakettransport gehört gegebenenfalls zur anderen Position; die jetzige Kategorie `postage` reicht zur Entscheidung nicht |
| Paketversand und Verpackung | Verpackung/Transport, Zeile 54, Kennzahl 227 | Art des Belegs und tatsächlicher betrieblicher Aufwand |
| Eingereichte Marktplatzkosten | Zuordnung nach konkreter Leistung: insbesondere Werbung oder übrige Betriebsausgaben als Vorschlag | Nicht jede Plattformgebühr ist dieselbe Leistung; keine automatische Zuordnung und kein Abrechnungsimport |
| Waren und unmittelbare Nebenkosten | Zeile 29, Kennzahl 100 | Abgrenzung zu Anlagevermögen, Privatnutzung und Spezialfällen |
| Homeoffice-Tagespauschale | Zeile 67, Kennzahl 163 | Bestätigte berechtigte Tage, Höchstbetrag und Ausschluss anderweitiger Doppelansätze; kein Geldabfluss |
| Abziehbare bezahlte Vorsteuer | Zeile 58, Kennzahl 185 | Nur bei bestehender Abzugsberechtigung; nicht einfach alle Belegsteuern summieren |
| Umsatzsteuer an/vom Finanzamt | Ausgaben Zeile 59, Kennzahl 186; Erstattungen Zeile 18, Kennzahl 141 | Tatsächliche Zahlung/Verrechnung und gegebenenfalls Zehn-Tage-Regel |
| Lieferanten-Erstattung | Bezug zur ursprünglichen Ausgabenposition als Zuordnungsvorschlag | Tatsächlicher Zufluss, Jahreswechsel und Umsatzsteuerfolgen |
| Vine-Zugänge/Entnahmen, AfA, weitere Einnahmen/Ausgaben | Separater späterer Ausbau | Bewertung, Erfassungszeitpunkt und Vermeidung von Doppelansätzen gemeinsam besprechen |

Entwurf einer späteren Ansicht: **Formularjahr → amtliche Position → enthaltene
Vorgänge → Herkunft und Betrag → noch ungeklärte Zuordnungen**. Nicht erfasste
Bereiche bleiben unbekannt, statt stillschweigend null zu werden. Die Ansicht
heißt zunächst „EÜR-Zuordnungsvorschlag“. Eine Freigabe der gesamten Steuererklärung
oder ELSTER-Übermittlung wird nicht behauptet. Reverse Charge wird erst nach
fachlicher Abstimmung umgesetzt; auch Kleinunternehmer können dabei betroffen sein.

## DATEV ist technisch möglich

Das DATEV-Format ist öffentlich dokumentiert: [Formatübersicht](https://developer.datev.de/de/file-format/details/datev-format/format-description),
[Header](https://developer.datev.de/de/file-format/details/datev-format/format-description/header),
[Buchungsstapel](https://developer.datev.de/de/file-format/details/datev-format/format-description/booking-batch)
und [offizielle Musterdatei](https://developer.datev.de/de/file-format/details/datev-format/format-description/sample-data).
Es handelt sich um eine lokale CSV-Dateischnittstelle mit definiertem Header und
Buchungsfeldern. Dafür ist keine direkte Übertragung an einen DATEV-Webdienst nötig.
Öffentliche Dokumentation ist keine Zusage einer Open-Source-Lizenz für DATEV-Produkte
oder einer Zertifizierung unseres Exports.

Für einen belastbaren Export fehlen zunächst fachlich bestätigte Konten und
Steuerschlüssel: Kontenrahmen/Kontenlänge, Mandanten-/Beraternummer, Wirtschaftsjahr,
Gegenkonten, Soll/Haben, Belegbezug, Erstattungen sowie Behandlung der Sonderfälle.
Rechnungen und Zahlungen dürfen nicht versehentlich doppelte Erlöse erzeugen.
Deshalb kein geratenes SKR03-/SKR04-Mapping einbauen.

Vorgeschlagene Umsetzung nach fachlicher Abstimmung: privates Exportprofil,
ausdrücklich unterstützte Fälle, gesonderte Liste aller nicht exportierbaren
Vorgänge, neue Ausgabe außerhalb beider Repos und technischer Validatorlauf.
Ein echter Importtest mit der empfangenden DATEV-Anwendung gehört vor eine
Kompatibilitätszusage. DATEV weist selbst darauf hin, dass eine reine Headerprüfung
keine vollständige Dateivalidierung ist: [Schnittstellenvorgaben](https://developer.datev.de/de/product-detail/accounting-extf-files/2.0/documentation/interface-requirements-file).

## Fachliche Grenzen

Das Werkzeug führt keine Betriebsprüfung und keinen steuerlichen Prüfbescheid.
Belegkontrolle und vollständige Exporte dienen der eigenen ordnungsgemäßen
Aufzeichnung und der späteren Prüfung durch Dritte. Die automatische
Verknüpfung von Zahlungsbewegungen mit archivierten Original-Zahlungsnachweisen
ist ausdrücklich außerhalb des Funktionsumfangs. Die vorhandene textliche
Zahlungsreferenz bleibt bestehen; erforderliche Zahlungsunterlagen werden
außerhalb dieses Verknüpfungsworkflows verfügbar gehalten.
