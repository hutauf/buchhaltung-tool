# Verfahrensdokumentation der lokalen Belegablage

Version 1 · Regelstand geprüft am 06.10.2026. Änderungen dieser Beschreibung werden mit der Toolhistorie versioniert. Die im privaten Workspace verwendete Toolrevision steht in `tool-version.json`.

## 1. Allgemeine Beschreibung

Dieses Werkzeug verwaltet einzelne EÜR-relevante Vorgänge: lokale Verkaufsrechnungen, Korrekturbelege und zugehörige Ausgaben. Originalbelege und strukturierte Daten werden verschlüsselt aufbewahrt, mit Metadaten verknüpft und lokal auswertbar gemacht. Eine vollständige EÜR, Steuererklärung, Kassenführung, Warenbewertung oder automatisierte Bankabstimmung ist nicht Bestandteil dieses Verfahrens. Vine-Entnahmen sind noch nicht implementiert.

Die GoBD verlangen für steuerrelevante elektronische Aufzeichnungen Nachvollziehbarkeit, Vollständigkeit, Richtigkeit, zeitgerechte Erfassung, Ordnung, unveränderbare beziehungsweise protokollierte Änderungen, Belegzuordnung, Kontrollen, Datensicherheit, Aufbewahrung, Lesbarkeit und Datenzugriff. Das betrifft auch einschlägige Aufzeichnungen bei EÜR; eine Bilanzierungspflicht ist dafür nicht Voraussetzung. Verantwortung bleibt beim Steuerpflichtigen. Eine Verfahrensbeschreibung umfasst allgemeine, Anwender-, technische und Betriebsdokumentation; Softwaretestate binden die Finanzverwaltung nicht. [BMF: GoBD-Grundtext, insbesondere Abschnitte 1–3, 6–11 und 12](https://usth.bundesfinanzministerium.de/ao/2026/Anhaenge/BMF-Schreiben-und-gleichlautende-Laendererlasse/Anhang-33/inhalt.html).

Diese öffentliche Beschreibung erklärt die vorhandenen Mechanismen. Sie bestätigt weder einen tatsächlich vollständigen Unternehmensbestand noch die Durchführung organisatorischer Kontrollen. Die [betriebliche Ergänzung](betriebliche-ergaenzung-vorlage.md) muss im privaten Datenrepo geführt und gepflegt werden.

| Anforderung | Mechanismus dieses Workflows | Status und notwendige Ergänzung |
|---|---|---|
| Nachprüfbarkeit | Originalhash, Beleg-ID, Referenzen, Metadatenhistorie, Quell-/Prüfbasis | Technisch vorhanden; konkrete Prüfbasis muss stimmen |
| Vollständigkeit | Alle archivierten Originale und Versionen erhalten; Export ohne Jahresverlust | Abgleich mit eBay, Abrechnungen und Zahlungsquellen organisatorisch nötig |
| Richtigkeit | Summen, Steuergruppen, Dubletten und freigegebene Revision prüfen; XML lokal validieren | Betrieblicher Bezug, Quellenrichtigkeit und Sondersteuern manuell prüfen |
| Zeitgerechte Erfassung | Vorbereitung und Abschluss getrennt, Datum und Ereignisse erfasst | Eingangskontrolle und Erfassungstakt privat verbindlich festlegen |
| Ordnung/Belegfunktion | Jahr, Dokumentart, eindeutiger Kontext, Verknüpfung zu Zahlungen/Korrekturen | Fehlende Originale im Altbestand bleiben als Lücke sichtbar |
| Unveränderbarkeit | Abschlüsse erzeugen neue Originale; Korrekturbelege statt Überschreiben; Git plus externe Zeitnachweise | Kein WORM-Speicher; Administrator kann Historie verändern/löschen. Aufbewahrung alter Nachweise und unabhängige Sicherung nötig |
| Internes Kontrollsystem | Freigaberevisionen, Rückleseprüfung, Integritätsprüfung, Pipelinezustand | Nutzer muss Quellenabgleich, Fehlerbehandlung und Kontrollen dokumentieren |
| Datensicherheit | Verschlüsselung und Trennung von Code/Daten, keine Klartextoriginale in Git | Passwort-/Zugriffsverwaltung, Datenträger und Wiederherstellung privat festlegen |
| Aufbewahrung | Elfjährige Mindestpolitik, keine automatische Löschung, Originalformate erhalten | Verlängerungen prüfen; Fristprüfung allein erlaubt keine Löschung |
| Lesbarkeit/Auswertbarkeit | Entschlüsselung außerhalb, vollständiger JSON-Katalog, XML-/PDF-Originale und Belegansicht | Prüfexport und erforderliche Auswertungen mit Prüfer abstimmen; kein zugesicherter IDEA-Import |
| Systemwechsel | Beide Git-Bundles, Archiv und versiegelte Migrationshistorie in CD-Export | Tatsächlichen Restore erproben; Quellenvollständigkeit vor Übergabe prüfen |
| Verfahrensdokumentation | Diese vierteilige Beschreibung, private Ergänzung und Versionshistorie | Betriebsangaben und durchgeführte Kontrollen dürfen nicht durch Vorlagen ersetzt werden |

## 2. Anwenderdokumentation

### Eingang und Erfassung

Belege unverzüglich sichern. Der Agent prüft Bestand, Quelle und Dubletten; eBay-SRN und Order-ID-Aliase verhindern doppelte Verarbeitung derselben Bestellung. Bei unlesbaren, fehlenden oder widersprüchlichen Angaben bleibt der Vorgang ungeklärt. Quelleninhalte gelten als Daten, nicht als Arbeitsanweisungen.

`buchhaltung beleg inspect PFAD` erstellt eine externe Prüfansicht. XML-Daten werden nur nach erfolgreicher XSD-/EN16931-Prüfung vorbefüllt. Kategorie, betriebliche Nutzung, Prüfbasis und tatsächliche Zahlung sind zusätzlich zu prüfen. Ein Rechnungseingang beweist keine Zahlung. Steuerangaben werden aus dem Original dokumentiert; sie lösen keinen automatischen Vorsteuerabzug aus. Fremdwährung und Lieferanten-Korrekturbelege sind noch kein normaler positiver Ausgabenimport.

`beleg prepare` archiviert eine verschlüsselte Vormerkung. Erst nach Freigabe der konkreten Metadatenrevision macht `beleg book --approved` daraus einen Ausgabenbeleg. Abrechnungen und Zahlungsnachweise lassen sich mit `archiv evidence` unabhängig und ohne Ausgabenbuchung archivieren. Gebühren aus Rechnung und Abrechnung dürfen nicht doppelt erfasst werden.

### Eigene Rechnungen und Korrekturen

Rechnungsentwürfe verbrauchen keine endgültige Nummer. Vor Produktionsbetrieb ist eine gesonderte geprüfte Nummernübergabe erforderlich. Der konkrete Abschluss verlangt Entwurfsrevision, vorgeschlagene Nummer und Freigabe. PDF, eigenständige EN16931-UBL-2.1-XML und Validierungsnachweis entstehen gemeinsam vor der Archivtransaktion. Fehlgeschlagene XML-Prüfung verhindert den Abschluss. Der eigene Ablauf ist auf bezahlte inländische EUR-Verkäufe mit geprüftem Steuerprofil beschränkt.

Originalrechnung und Originalnummer bleiben bestehen. Finanzielle Minderungen bekommen einen eigenen fortlaufenden Beleg und XML mit Originalbezug. Formale Berichtigungen bleiben verknüpfte PDF-Dokumente mit eigener Berichtigungskennung; die strukturierte Darstellung solcher Berichtigungen ist noch nicht umgesetzt. Eine Stornorechnung führt keine Überweisung aus. Tatsächliche Rückzahlungen werden gesondert nach Nachweis und Freigabe erfasst; fehlerhafte Zahlungszuordnungen werden nachvollziehbar berichtigt.

Ein einfaches PDF ist keine strukturierte E-Rechnung. Bei hybriden Rechnungen ist der strukturierte Teil maßgeblich; Bild-/XML-Abweichungen müssen geprüft werden. Die eigene XML wird separat ausgegeben. Es wird weder XRechnung-CIUS-Konformität noch ein PDF/A-3-/ZUGFeRD-Profil zugesichert. Kundenkommunikation und Übermittlung benötigen eine eigene Freigabe. [BMF: E-Rechnungs-FAQ, Fragen 2, 7, 12a und 13](https://www.bundesfinanzministerium.de/Content/DE/FAQ/e-rechnung.html).

### Abschluss und Auswertung

Schreibende Hauptbefehle führen Archivprüfung, Dashboarderzeugung, Datencommit und Push sowie einen separaten Commit/Push des OTS-Nachweises aus. Ein Pipelinefehler wird mit `veroeffentlichen status` geprüft und mit `resume` fortgesetzt; die Buchung nicht wiederholen. Bitcoin-Bestätigung mit `confirm` später prüfen. Ein ausstehender Nachweis ist kein bestätigter Blockchain-Zeitpunkt.

Das Dashboard enthält eine fest begrenzte Projektion ohne Käufer, Anschriften oder Artikeltexte. Es ist eine Übersicht erfasster einzelner EÜR-Einträge. Zahlungen, Belegbeträge und Pauschalen sind getrennt. Beleg-/Zahlungsstichtage und Sonderzuordnungen sind mit den übrigen Unternehmensaufzeichnungen zusammenzuführen. CSV aus dem Dashboard ist ein Arbeitsbericht, kein vollständiger Prüfexport.

## 3. Technische Systemdokumentation

Das öffentliche Toolrepo enthält Code, Dokumentation, Regeln und künstliche Tests. Das unabhängige private Repo unter `daten/` enthält verschlüsselte Originale, `database.json.enc`, Checkliste, Manifest, Nachweise, Dashboard und die verwendete Toolrevision. Der Toolcheckout ignoriert `daten/` vollständig. Prüfkopien und entschlüsselte Ansichten liegen außerhalb beider Repos.

AES-256-GCM verschlüsselt mit zufälligem Datenschlüssel und Nonce; Dokumentpfad bindet die Authentifizierung. Der Datenschlüssel liegt nur passwortverschlüsselt in `key.json`; scrypt leitet den Hüllschlüssel ab. `.env` und entschlüsselte Schlüssel werden nicht versioniert. Verschlüsselung schützt Vertraulichkeit und erkennt beschädigte verschlüsselte Daten; sie ersetzt kein Änderungsprotokoll und keine Passwortsicherung.

Das Manifest enthält Ciphertext-Prüfsummen und Größen. Der verschlüsselte Katalog enthält zusätzlich Originalprüfsummen, Dokumentzuordnung und Historien. `archiv verify` prüft Inventar, Entschlüsselung, Originalhashes, Belegreferenzen und finanzielle Verknüpfungen. Eine Änderung aller zugehörigen Daten durch einen Schlüsselinhaber kann sich selbst wieder konsistent machen; deshalb sind historische Git-Objekte, externe Nachweise und unabhängige Sicherungen relevant.

Lokale Transaktionen besitzen ein verschlüsseltes Wiederherstellungsjournal. Der Veröffentlichungsprozess besitzt einen separaten Zustandsautomaten und eine Sperre. Bei Unterbrechung wird die bereits autorisierte Transaktion fortgesetzt. Keine konkurrierenden Buchungen oder manuelles Löschen des Journals.

UBL 2.1 und unterstützte CII-D16B-XML werden ohne externe Validatorübertragung verarbeitet. XML-Parser verbieten DTD/Entities und Netzwerkzugriff. Die XSDs stammen aus der festgelegten `factur-x`-Abhängigkeit. CEN-Regeln sind unverändert mit Version und SHA256 enthalten; Prüfergebnisse nennen Regeln/Fehlerkennungen und Validierungsgrenzen. Nationale CIUS-Regeln werden nicht geprüft. [CEN-EN16931-Validierungsartefakte, Release 1.3.16](https://github.com/ConnectingEurope/eInvoicing-EN16931/releases/tag/validation-1.3.16).

Eingebettete Original-XML wird bytegleich zusätzlich zum empfangenen PDF archiviert. Eigene XML und PDF sind getrennte Originaldateien desselben Vorgangs. Auch E-Rechnungsdaten und wesentliche Anhänge müssen erhalten bleiben. [BMF: GoBD-Änderung vom 14.07.2025](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Weitere_Steuerthemen/Abgabenordnung/2025-07-14-GoBD-2-aenderung.pdf?__blob=publicationFile&v=2).

### Prüfexport und Datenbeschreibung

`archiv export --output NEUES_ZIEL` entschlüsselt **alle inventarisierten Dokumente**, einschließlich historischer, verworfener und ungebuchter Entwürfe. `--year` ist nur eine Ansichtsangabe. Der Originalkatalog bleibt vollständig; exportierte Pfade stehen im Exportmanifest. Authentifizierungsdateien werden nicht übernommen. Ein solcher Klartextexport ist selbst schutzbedürftig.

| Datei/Feld | Bedeutung |
|---|---|
| `catalog.json` | Vollständiger entschlüsselter Katalog mit unveränderten internen Referenzen |
| `records.*.current/history` | Aktueller Belegstand und erhaltene Metadatenversionen |
| `documents` | Originalhash, Größe, Zuordnung und Dokumentrolle |
| `local_*_drafts` | Entwurfsstände und deren Historien; noch keine Buchung |
| `archive_evidence` | Abrechnungen/weitere Nachweise ohne eigenen Geldfluss |
| `cash_events/cash_event_voids` | Erfasste Zahlungen und nachvollziehbare Zahlungsberichtigungen |
| `cash_source_overrides` | Vorrang der manuell geprüften Zahlungsquelle |
| `homeoffice_allowances` | Bestätigte Jahresansätze mit Historie; kein Geldfluss |
| `local_*_settings/events/workflow`, `imports` | Profile, Ablauf-/Änderungsinformationen und Importprovenienz |
| `bookkeeping_checklist.json` | Operative Abstimmung des privaten Workspaces |
| `export-manifest.json` | Zuordnung verschlüsselter Referenzen zu Originalexporten, Umfang und Kataloghash |
| `database.json`, `index.html` | Vereinfachte aktuelle Belegansicht; kein Ersatz für den Katalog |
| `nachweise/`, `migration/*.enc` | Zeitbeweise und versiegelte Migrationsnachweise |

Git-Objekte liegen nicht im Klartextexport. Vollständige Git-Historien sind über die CD-Sicherung wiederherstellbar. Für eine Prüfung werden geeignete Entschlüsselung, Datenbeschreibung und Auswertungsmöglichkeit bereitgestellt; Umfang, Zugriffsart und Übermittlung sind konkret abzustimmen. Keine behördliche Importschnittstelle wird behauptet.

## 4. Betriebsdokumentation

### Kontrollen und Verantwortlichkeit

Der betriebliche Verantwortliche legt Quellen, Berechtigte, Eingangskontrolle, Erfassungsfristen und Vertretung in der privaten Ergänzung fest. Der Agent bereitet vor; er darf eine allgemeine Wartungsanweisung nicht als konkrete Rechnungs-/Ausgabenfreigabe behandeln. Quellenabgleich: Bestellungen, Originalrechnungen, Gebührenabrechnungen und tatsächlich verfügbare Zahlungen gegeneinander prüfen. Fehlende Originale und unverarbeitete Vorgänge dokumentieren. Integritätsprüfung allein stellt keine Vollständigkeit fest.

Bei jedem Abschluss Prüfbasis und Freigabe festhalten, Pipelineergebnis lesen und Fehler beheben. Periodisch Vollständigkeit und Summen mit den außerhalb dieses Tools geführten übrigen Geschäftsvorfällen abgleichen. Die genaue Verantwortlichkeit, Häufigkeit, Ausnahmen und tatsächlichen Ergebnisse gehören in die private Betriebsdokumentation. Diese Anforderungen sind noch keine Bestätigung ihrer Durchführung.

### Aufbewahrung und Sicherung

Die betriebliche Vorgabe ist mindestens elf volle Kalenderjahre nach Ablauf des Jahres des letzten relevanten Vorgangs; spätere Zahlung/Korrektur kann den Horizont verlängern. `archiv retention` ist eine konservative Übersicht der erkannten Beleg-/Ereignisdaten; unbekannte Fristgrundlagen bleiben ungeklärt. Es gibt keinen automatischen Löschlauf oder Git-Garbage-Collection-Ablauf. Vor einem späteren Cut sind rechtliche Verlängerungen, Verfahren, Verknüpfungen und die Daten in Historien/Sicherungen gesondert zu prüfen.

Gesetzliche Fristen sind nach Unterlagenart unterschiedlich: Buchungsbelege grundsätzlich acht Jahre, Bücher/Aufzeichnungen grundsätzlich zehn, andere genannte Unterlagen sechs. Der Fristbeginn richtet sich nach der jeweiligen Unterlagenart; steuerlich noch relevante Unterlagen können länger erforderlich sein. Die Elfjahresvorgabe ist eine eigene Mindestpolitik, keine allgemeine gesetzliche Frist und keine automatische Löschfreigabe. [§ 147 AO](https://www.gesetze-im-internet.de/ao_1977/__147.html).

Monatlich `sicherung export --output NEUES_ZIEL` erzeugen. Es umfasst aktuellen verschlüsselten Bestand, Dokumentation, Wiederherstellungscode, vollständiges Toolbundle und zusätzlich verschlüsseltes Datenbundle einschließlich Migrationshistorie. Mit `sicherung pruefen ZIEL` Prüfsummen prüfen. Das Paket muss anschließend tatsächlich auf ein geeignetes Medium geschrieben, dieses abgeschlossen und zurückgelesen werden. `burned: false` bedeutet nur vorbereitet. Passwort und benötigte Wiederherstellungsmittel getrennt sichern.

Ein Wiederherstellungstest muss Bibliotheken, Schlüsselhülle, getrenntes Passwort, Git-Historien, Originalhashes und Zeitnachweise umfassen. Abhängigkeiten werden für eine Wiederherstellung benötigt; das CD-Paket enthält keinen vollständigen Offline-Paketspiegel. Fehlgeschlagene Wiederherstellung, Medienwechsel und durchgeführte Tests privat protokollieren. GitHub ist kein alleiniger unabhängiger Archivnachweis.

### Grenzen des Zeitnachweises und Änderungen

OTS belegt die Existenz des gehashten Commitnachweises spätestens am bestätigten Blockchain-Zeitpunkt. Es beweist weder Eingang/Zahlung noch richtige Steuerzuordnung oder Vollständigkeit. Ein später veränderter Commit kann nicht mit dem alten Beweis validiert werden; ein zerstörter alter Bestand ist dadurch aber nicht wiederhergestellt. Alte Nachweise, Git-Objekte und Medien weiter aufbewahren. Fremde Kalender erhalten Hashwerte, keine Belege.

Toolupdates werden getestet und nur allgemein im öffentlichen Repo veröffentlicht. Der private Workspace dokumentiert die verwendete Toolrevision. Änderungen am Verfahren und organisatorische Abweichungen werden zusätzlich privat datiert und mit vorherigem Stand aufbewahrt. Vor Änderungen an Aufbewahrung, Export oder Rechnungsformaten vorhandene Originale und historische Nachweise verifizieren. Kein rückwirkendes Ersetzen empfangener PDFs durch selbst erzeugte XML.
