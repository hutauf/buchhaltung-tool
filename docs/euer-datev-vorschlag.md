# Vorschlag: Anlage EÜR und DATEV

Stand 21.10.2026. Die amtliche EÜR-Feldzuordnung bleibt ein fachlicher Vorschlag
zur Besprechung. Der [DATEV-Export für 2026](datev-export.md) ist inzwischen vorhanden;
er ist von einer abgabefertigen amtlichen EÜR zu unterscheiden.
Der bestehende Jahresbericht wertet die tatsächlich erfassten Daten aus und
enthält den vollständigen Original-/JSON-/CSV-Export.

Der geplante Ablauf ist eine einfache Einnahmen-/Ausgabenaufzeichnung für
Kleinunternehmer nach § 19 UStG. Nutzer verwalten Kategorien und EÜR-Positionen,
keinen Kontenrahmen. Neue eigene Rechnungen mit Regelbesteuerung sind gesperrt.
Amazon-/Vine-Produkttester-Leistungsumsätze, insbesondere ausgehende
Reverse-Charge-Umsätze, werden vorerst nicht aufgenommen.

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
| Software-Abos | Laufende EDV-Kosten, Zeile 51, Kennzahl 228, als Ausgangsvorschlag | Laufender Aufwand versus Anschaffung/Lizenz; betrieblicher Anteil; ausländische Eingangsleistungen und Sondersteuern nicht automatisch verarbeiten |
| Briefporto/Büromaterial | Arbeitsmittel, Zeile 52, Kennzahl 229 | Pakettransport gehört gegebenenfalls zur anderen Position; die jetzige Kategorie `postage` reicht zur Entscheidung nicht |
| Paketversand und Verpackung | Verpackung/Transport, Zeile 54, Kennzahl 227 | Art des Belegs und tatsächlicher betrieblicher Aufwand |
| Eingereichte Marktplatzkosten | Zuordnung nach konkreter Leistung: insbesondere Werbung oder übrige Betriebsausgaben als Vorschlag | Nicht jede Plattformgebühr ist dieselbe Leistung; keine automatische Zuordnung und kein Abrechnungsimport |
| Waren und unmittelbare Nebenkosten | Zeile 29, Kennzahl 100 | Abgrenzung zu Anlagevermögen, Privatnutzung und Spezialfällen |
| Homeoffice-Tagespauschale | Zeile 67, Kennzahl 163 | Bestätigte berechtigte Tage, Höchstbetrag und Ausschluss anderweitiger Doppelansätze; kein Geldabfluss |
| Lieferanten-Erstattung | Bezug zur ursprünglichen Ausgabenposition als Zuordnungsvorschlag | Tatsächlicher Zufluss, Jahreswechsel und Umsatzsteuerfolgen |
| Vine-Zugänge/Entnahmen, AfA, weitere Einnahmen/Ausgaben | Separater späterer Ausbau | Bewertung, Erfassungszeitpunkt und Vermeidung von Doppelansätzen gemeinsam besprechen |

Entwurf einer späteren Ansicht: **Formularjahr → amtliche Position → enthaltene
Vorgänge → Herkunft und Betrag → noch ungeklärte Zuordnungen**. Nicht erfasste
Bereiche bleiben unbekannt, statt stillschweigend null zu werden. Die Ansicht
heißt zunächst „EÜR-Zuordnungsvorschlag“. Eine Freigabe der gesamten Steuererklärung
oder ELSTER-Übermittlung wird nicht behauptet. Reverse Charge wird erst nach
fachlicher Abstimmung für Produkttester-Leistungsumsätze erweitert. Diese Einnahmen
bleiben jetzt außerhalb des Tools. Eingangsbelege behalten ihre ausgewiesenen
Steuerangaben; daraus wird kein automatischer Vorsteuerabzug abgeleitet.

## DATEV ist technisch möglich

Das DATEV-Format ist öffentlich dokumentiert: [Formatübersicht](https://developer.datev.de/de/file-format/details/datev-format/format-description),
[Header](https://developer.datev.de/de/file-format/details/datev-format/format-description/header),
[Buchungsstapel](https://developer.datev.de/de/file-format/details/datev-format/format-description/booking-batch)
und [offizielle Musterdatei](https://developer.datev.de/de/file-format/details/datev-format/format-description/sample-data).
Es handelt sich um eine lokale CSV-Dateischnittstelle mit definiertem Header und
Buchungsfeldern. Dafür ist keine direkte Übertragung an einen DATEV-Webdienst nötig.
Öffentliche Dokumentation ist keine Zusage einer Open-Source-Lizenz für DATEV-Produkte
oder einer Zertifizierung unseres Exports.

DATEV unterstützt auch die Gewinnermittlung per EÜR, siehe
[DATEV EÜR Steuern](https://www.datev.de/web/de/berufsgruppenuebergreifend/service-und-support/umstellungen/auf-datev-euer-steuern).
Eine EÜR setzt beim Nutzer keine doppelte Buchführung voraus. Der hier untersuchte
DATEV-Buchungsstapel verlangt jedoch technisch Konto, Gegenkonto und Soll/Haben.
Die Schnittstellenanforderung ist von unserer einfachen Aufzeichnung zu trennen.

Der [DATEV-Exportadapter](datev-export.md) nutzt jetzt ein festgelegtes SKR03-EÜR-Profil
für 2026 und das neutrale EÜR-Verrechnungskonto 1371. Die Anwendung selbst bleibt
bei Einnahmen-/Ausgabenkategorien. Im Dashboard entstehen DATEV-CSV und ein
Begleitbericht als ZIP, ohne Datenbuchung. Echte Zielnummern des Empfängers werden
im Dialog eingegeben; sie werden nicht geraten. Bekannte Ausnahmen werden separat
ausgewiesen. Ein Import bloßer EÜR-Zeilensummen in DATEV EÜR Steuern wird weiterhin
nicht behauptet. Vorhanden sind lokaler Formatprüfer und Browser-/CLI-Vergleich;
ein echter Importtest in DATEV ist nicht erfolgt.

## Fachliche Grenzen

Das Werkzeug führt keine Betriebsprüfung und keinen steuerlichen Prüfbescheid.
Belegkontrolle und vollständige Exporte dienen der eigenen ordnungsgemäßen
Aufzeichnung und der späteren Prüfung durch Dritte. Die automatische
Verknüpfung von Zahlungsbewegungen mit archivierten Original-Zahlungsnachweisen
ist ausdrücklich außerhalb des Funktionsumfangs. Die vorhandene textliche
Zahlungsreferenz bleibt bestehen; erforderliche Zahlungsunterlagen werden
außerhalb dieses Verknüpfungsworkflows verfügbar gehalten.
