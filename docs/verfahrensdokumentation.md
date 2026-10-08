# Verfahrensdokumentation der lokalen Belegablage

Version 4 · Technikstand 08.10.2026, rechtliche Grundlagen zuletzt geprüft am 07.10.2026. Änderungen dieser Beschreibung werden mit der Toolhistorie versioniert. Die im privaten Workspace verwendete Toolrevision steht in `tool-version.json`.

## 1. Allgemeine Beschreibung

Dieses Werkzeug verwaltet einzelne EÜR-relevante Vorgänge: lokale Verkaufsrechnungen, Korrekturbelege und zugehörige Ausgaben. Originalbelege und strukturierte Daten werden verschlüsselt aufbewahrt, mit Metadaten verknüpft und lokal auswertbar gemacht. Eine vollständige EÜR, Steuererklärung, Kassenführung, Warenbewertung oder automatisierte Bankabstimmung ist nicht Bestandteil dieses Verfahrens. Vine-Entnahmen sind noch nicht implementiert.

Die GoBD verlangen für steuerrelevante elektronische Aufzeichnungen Nachvollziehbarkeit, Vollständigkeit, Richtigkeit, zeitgerechte Erfassung, Ordnung, unveränderbare beziehungsweise protokollierte Änderungen, Belegzuordnung, Kontrollen, Datensicherheit, Aufbewahrung, Lesbarkeit und Datenzugriff. Das betrifft auch einschlägige Aufzeichnungen bei EÜR; eine Bilanzierungspflicht ist dafür nicht Voraussetzung. Verantwortung bleibt beim Steuerpflichtigen. Eine Verfahrensbeschreibung umfasst allgemeine, Anwender-, technische und Betriebsdokumentation; Softwaretestate binden die Finanzverwaltung nicht. [BMF: GoBD-Grundtext, insbesondere Abschnitte 1–3, 6–11 und 12](https://usth.bundesfinanzministerium.de/ao/2026/Anhaenge/BMF-Schreiben-und-gleichlautende-Laendererlasse/Anhang-33/inhalt.html).

Diese öffentliche Beschreibung erklärt die vorhandenen Mechanismen. Sie bestätigt weder einen tatsächlich vollständigen Unternehmensbestand noch die Durchführung organisatorischer Kontrollen. Die [betriebliche Ergänzung](betriebliche-ergaenzung-vorlage.md) muss im privaten Datenrepo geführt und gepflegt werden.

| Anforderung | Mechanismus dieses Workflows | Status und notwendige Ergänzung |
|---|---|---|
| Nachprüfbarkeit | Originalhash, Beleg-ID, Referenzen, Metadatenhistorie, Quell-/Prüfbasis | Technisch vorhanden; konkrete Prüfbasis muss stimmen |
| Vollständigkeit | Alle archivierten Originale und Versionen erhalten; Export ohne Jahresverlust; gespeicherter eBay-Verkaufsabgleich | API-Zeitfenster umfasst nicht alle Unternehmensdaten; fehlende Kosten und tatsächliche Zahlungsquellen gesondert prüfen |
| Richtigkeit | Summen, Steuergruppen, Dubletten und freigegebene Revision prüfen; XML lokal validieren | Betrieblicher Bezug, Quellenrichtigkeit und Sondersteuern manuell prüfen |
| Zeitgerechte Erfassung | Vorbereitung und Abschluss getrennt, Datum und Ereignisse erfasst | Eingangskontrolle und Erfassungstakt privat verbindlich festlegen |
| Ordnung/Belegfunktion | Jahr, Dokumentart, eindeutiger Kontext, Verknüpfung zu Zahlungen/Korrekturen | Fehlende Originale im Altbestand bleiben als Lücke sichtbar |
| Unveränderbarkeit | Neue Originale statt Überschreiben; zentrale Original-/Inventarsperre; verschlüsseltes Katalogänderungsprotokoll plus Git/OTS | Kein WORM-Speicher; Administrator kann Historie verändern/löschen. Aufbewahrung alter Nachweise und unabhängige Sicherung nötig |
| Internes Kontrollsystem | Freigaberevisionen, Rückleseprüfung, Integritätsprüfung und gespeicherter technischer Kontrollnachweis vor Datenveröffentlichung | Nutzer muss Quellenabgleich, Fehlerbehandlung und betriebliche Kontrollen dokumentieren |
| Datensicherheit | Verschlüsselung und Trennung von Code/Daten, keine Klartextoriginale in Git | Passwort-/Zugriffsverwaltung, Datenträger und Wiederherstellung privat festlegen |
| Aufbewahrung | Elfjährige Mindestpolitik, keine automatische Löschung, Originalformate erhalten | Verlängerungen prüfen; Fristprüfung allein erlaubt keine Löschung |
| Lesbarkeit/Auswertbarkeit | Entschlüsselung außerhalb, vollständiger JSON-/CSV-Katalog, Feldtypen/Verknüpfungen, XML-/PDF-Originale und Belegansicht | Prüfexport und erforderliche Auswertungen mit Prüfer abstimmen; kein zugesicherter IDEA-Import |
| Systemwechsel | Beide Git-Bundles, Archiv und versiegelte Migrationshistorie in CD-Export; isolierter Restoretest im Register | Neuinstallation der Abhängigkeiten und Blockchainprüfung separat erproben; Quellenvollständigkeit vor Übergabe prüfen |
| Verfahrensdokumentation | Diese vierteilige Beschreibung, private Ergänzung und Versionshistorie | Betriebsangaben und durchgeführte Kontrollen dürfen nicht durch Vorlagen ersetzt werden |

## 2. Anwenderdokumentation

Einrichtung und Zugangskonfiguration stehen in der [Einrichtungsanleitung](einrichtung.md); die vollständige Befehlsreferenz im [Handbuch](handbuch.md). Die README fasst Einstieg, GoBD-Kontrollen und Grenzen zusammen. Diese redaktionelle Aufteilung ändert das Verfahren nicht. Die Anbindungsanleitung benennt die bestehende zusätzliche Vine-Voraussetzung für eBay-Rechnungsentwürfe ausdrücklich.

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

### Lieferanten-Korrekturen und tatsächliche Erstattungen

Ein empfangener Storno-/Minderungsbeleg wird über denselben Belegeingang gelesen, geprüft, vorgemerkt und nach konkreter Freigabe gebucht. Seine Metadaten geben `document_type: supplier_credit`, `original_id` und `correction_reason` an. Beträge im geprüften Eingabeformular sind positive Nennbeträge. Im gebuchten Bestand erhält er die Art `expense_credit` und negative Brutto-/Netto-/Steuerbeträge. Die eigene Rechnungsnummernfolge wird nicht verwendet. Die Originalausgabe samt Nummer und Originaldateien bleibt unverändert. Lieferant, Originalbezug, Datum, Währung, verbleibende Brutto-/Netto-/Steuerbeträge und vorhandene Steuergruppen werden geprüft. Die Summe aller Minderungen darf die Originalbeträge nicht überschreiten. Ein UBL/CII-Minderungsbeleg wird als solcher erkannt; XML und freigegebene Metadaten müssen übereinstimmen. Nationale CIUS-Prüfung bleibt eine Grenze.

Der Minderungsbeleg allein bewirkt keinen Geldfluss. Eine tatsächlich zugeflossene Erstattung wird mit Datum, positivem Betrag und konkretem Zahlungsnachweis im Ausgabenbereich erfasst und mindert dort die Zahlungs-Ausgaben. Verrechnung mit noch offenen Forderungen ist kein behaupteter Bankzufluss; solche Fälle müssen anhand der tatsächlichen Zahlungslage gesondert zugeordnet werden. Manuelle Zuordnungen ersetzen die zuvor verwendete Zahlungsquelle des betreffenden Belegs; der Helfer summiert beide Quellen nicht doppelt. Keine Zahlung wird vom Tool ausgeführt.

Bei einer Originalausgabe zeigt das Dashboard den Befehl „Lieferanten-Korrektur einlesen“. Dieser löst die anonyme Referenz nur im privaten Workspace auf und übergibt die vorhandene Original-ID an `beleg inspect --original-id ID`. So ist der Originalbezug bereits in der externen Prüfformularvorlage gesetzt; es wird dadurch keine Buchung freigegeben.

### Automatischer eBay-Verkaufsabgleich

`abgleich ebay --days 90 --save` liest Verkäuferbestellungen mit bezahlten und unbezahlten Zuständen, sortiert absteigend und ruft alle Ergebnisseiten eines beim Abrufbeginn festgehaltenen Erstellungszeitfensters ab. Pro Seite werden höchstens 100 Einträge angefordert. Der Endzeitpunkt liegt zwei Minuten zurück, um frisch angelegte, noch inkonsistente Kombibestellungen auszuschließen; der nächste überlappende Abruf erfasst diese. Auch am Beginn bleiben zwei Minuten Abstand zur historischen API-Grenze. Für vollständige Abrufe werden `CreateTimeFrom/CreateTimeTo` genutzt; `NumberOfDays` ist auf 30 begrenzt. Ohne bestätigten vollständigen Seitenabruf wird kein erfolgreicher Abgleich gespeichert. Das maximal unterstützte Fenster umfasst annähernd 90 Tage; ältere Quellenlücken können dadurch nicht ausgeschlossen werden. Der tägliche Betrieb muss diesen Helfer ausdrücklich aufrufen; ein API-Client allein ist kein laufender Hintergrunddienst. [eBay: GetOrders](https://developer.ebay.com/devzone/xml/docs/reference/ebay/getorders.html).

Der Abgleich verbindet Bestellungen über SRN, bekannte Order-ID-Aliasse oder vollständige, exakte Transaktionskennungen mit Rechnungen und Checkliste. Titelähnlichkeit ist kein Verknüpfungskriterium. Ergebnisse unterscheiden unbezahlte Vorgänge, passende Archivbelege, abweichende Beträge, Mehrdeutigkeiten, Entwürfe, lediglich externe Referenzen, fehlende Rechnungen, fehlende Originale und ausdrücklich private Vorgänge. Eine externe Checklistenreferenz beweist kein im neuen Archiv vorhandenes Original. Bei parallel weiterlaufender bisheriger Buchhaltung kann `--checklist PFAD` deren aktuelle operative Checkliste ausschließlich lesend heranziehen. Eine verschlüsselte Kopie samt Prüfsumme bleibt beim Abgleichnachweis; keine Finanzdaten werden daraus übernommen. Nicht zurückgegebene ältere Bestellungen werden nicht automatisch als fehlend oder gelöscht behandelt.

Zeitpunkt, Fenster, Seitenzahl, Ergebnisse und empfangene API-XML werden verschlüsselt unter `ebay_reconciliations` und als Originalnachweise gespeichert, protokolliert und über die normale private Git-/OTS-Pipeline veröffentlicht. Finanzielle Buchungen und externe Systeme werden dabei nicht verändert. Das Dashboard zeigt nur Zeitpunkt, Umfang und erlaubte Statuszählungen; nach mehr als zwei Tagen ohne gespeicherten Abruf warnt es. Es greift selbst nicht auf eBay zu.

Ein automatischer Import von eBay-Abrechnungen, Gebühren oder Auszahlungen gehört ausdrücklich nicht zum vereinbarten Umfang. Kosten werden nur anhand separat eingereichter und freigegebener Belege erfasst. Der Verkaufsabgleich ist keine Bank-/Auszahlungsabstimmung und kein Nachweis vollständiger Betriebsausgaben. Nicht erfasste Ausgaben und übrige Unternehmensaufzeichnungen bleiben eine dokumentierte Grenze; daraus folgt keine allgemeine Aussage über die Zulässigkeit unvollständiger steuerrelevanter Aufzeichnungen.

### Änderungs- und Verarbeitungsprotokolle

Jeder über den Kataloghelfer gespeicherte Datenbankwechsel ergänzt `audit_trail` innerhalb des verschlüsselten Katalogs. Ein Eintrag hält UTC-Erfassungszeit, technische Schreiberkennung `local-helper`, Tool-Gitrevision, vorherigen/nachfolgenden Kataloghash und Änderungen mit Pfad sowie Vorher-/Nachher-Werten fest. Die Einträge sind fortlaufend nummeriert und über SHA256 verkettet. Die Archiv- und Indexprüfung rekonstruiert den Stand aus Ausgangsbestand und Änderungen; Kürzung, veränderte Einträge oder Abweichungen zum aktuellen Katalog werden beanstandet. Das Transaktionsjournal enthält bereits den vorbereiteten Eintrag, sodass Wiederaufnahme ihn nicht doppelt erzeugt. Tatsächliche menschliche Freigabe und betriebliche Prüfung folgen weiterhin den konkreten Workflow-Nachweisen; die technische Schreiberkennung ist kein Personen- oder Identitätsnachweis.

Vorhandene Archive ohne `audit_trail` bleiben lesbar. Bei der nächsten Katalogänderung wird ihr Ausgangsbestand als `existing_state` erhalten. Frühere Eingangstermine oder Kontrollhandlungen werden nicht rückwirkend behauptet. Die Protokollzeit belegt die lokale Verarbeitung, nicht automatisch den früheren E-Mail-Eingang. Separat gespeicherte Checklistenänderungen bleiben über die verschlüsselte Datei und Git-Historie prüfbar; sie sind keine Katalogänderungsereignisse. Direktmanipulationen außerhalb der Helfer sind nicht durch eine Anwendungssperre verhindert; unabhängige Zeitnachweise und Sicherungen bleiben erforderlich.

Vor einem neuen Datencommit speichert die Veröffentlichung unter `processing_controls` einmalig je Pipelinekennung die tatsächlich bestandene Archiv-Integritätsprüfung mit Datum, Toolrevision, geprüftem Kataloghash und Beleg-/Dokumentanzahl. Auch dieser Nachweis wird verschlüsselt, protokolliert und im Datencommit verankert. Er behauptet ausdrücklich keinen vollständigen Quellenabgleich. Unveränderte Leseprüfungen und reine OTS-Nachweiscommits verändern den Katalog nicht. Fehler bleiben über Pipeline-/Transaktionszustand sichtbar; deren Ursachen und Behebung sind zusätzlich betrieblich nachzuweisen. Quellenabgleich und Wiederherstellungstests sind weiterhin durchzuführen und separat zu dokumentieren. [BMF: GoBD, Rz. 59–60, 88, 100, 107–117](https://ao.bundesfinanzministerium.de/ao/2026/Anhaenge/BMF-Schreiben-und-gleichlautende-Laendererlasse/Anhang-33/inhalt.html).

Die zentrale Schreibfunktion erlaubt bei Originaldateien ausschließlich das erneute Schreiben identischer Bytes. Der Kataloghelfer verbietet die Entfernung vorhandener Dokumentreferenzen sowie die Änderung ihrer Originalhashes oder Größen. Korrekturen bekommen neue Originale und bleiben verknüpft. Das ist eine zusätzliche Anwendungskontrolle, keine physische WORM-Sperre des Dateisystems.

UBL 2.1 und unterstützte CII-D16B-XML werden ohne externe Validatorübertragung verarbeitet. XML-Parser verbieten DTD/Entities und Netzwerkzugriff. Die XSDs stammen aus der festgelegten `factur-x`-Abhängigkeit. CEN-Regeln sind unverändert mit Version und SHA256 enthalten; Prüfergebnisse nennen Regeln/Fehlerkennungen und Validierungsgrenzen. Nationale CIUS-Regeln werden nicht geprüft. [CEN-EN16931-Validierungsartefakte, Release 1.3.16](https://github.com/ConnectingEurope/eInvoicing-EN16931/releases/tag/validation-1.3.16).

Eingebettete Original-XML wird bytegleich zusätzlich zum empfangenen PDF archiviert. Eigene XML und PDF sind getrennte Originaldateien desselben Vorgangs. Auch E-Rechnungsdaten und wesentliche Anhänge müssen erhalten bleiben. [BMF: GoBD-Änderung vom 14.07.2025](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Weitere_Steuerthemen/Abgabenordnung/2025-07-14-GoBD-2-aenderung.pdf?__blob=publicationFile&v=2).

### Prüfexport und Datenbeschreibung

`archiv export --output NEUES_ZIEL` entschlüsselt **alle inventarisierten Dokumente**, einschließlich historischer, verworfener und ungebuchter Entwürfe. `--year` ist nur eine Ansichtsangabe. Der Originalkatalog bleibt vollständig; exportierte Pfade stehen im Exportmanifest. Authentifizierungsdateien werden nicht übernommen. Ein solcher Klartextexport ist selbst schutzbedürftig.

| Datei/Feld | Bedeutung |
|---|---|
| `catalog.json` | Vollständiger entschlüsselter Katalog mit unveränderten internen Referenzen |
| `catalog-nodes.csv` | Jeder Katalogwert und Container mit Typ, RFC6901-Pfad, Elternpfad und Schlüssel; einschließlich Historien und Protokollen |
| `records.csv` | Belege und Entwürfe mit aktuellen/historischen Ständen, Textnummern, Beträgen und Katalogverweis |
| `documents.csv`, `record-documents.csv` | Originalreferenzen, Exportpfade, Hashes, Größen und versionierte Beleg-/Originalverknüpfungen |
| `data-description.json` | Maschinenlesbare Spaltenbeschreibungen, Feldtypen, UTF-8/CSV-Format und Tabellenprüfsummen |
| `records.*.current/history` | Aktueller Belegstand und erhaltene Metadatenversionen |
| `documents` | Originalhash, Größe, Zuordnung und Dokumentrolle |
| `local_*_drafts` | Entwurfsstände und deren Historien; noch keine Buchung |
| `archive_evidence` | Abrechnungen/weitere Nachweise ohne eigenen Geldfluss |
| `cash_events/cash_event_voids` | Erfasste Zahlungen und nachvollziehbare Zahlungsberichtigungen |
| `cash_source_overrides` | Vorrang der manuell geprüften Zahlungsquelle |
| `homeoffice_allowances` | Bestätigte Jahresansätze mit Historie; kein Geldfluss |
| `audit_trail` | Erhaltener Ausgangsbestand, verkettete Katalogänderungen mit Vorher-/Nachher-Werten und Toolrevision |
| `processing_controls` | Durchgeführte technische Archivprüfung vor Veröffentlichung; kein Vollständigkeitsnachweis |
| `ebay_reconciliations` | Vollständige API-Abrufe im begrenzten Zeitfenster mit verschlüsselten Originalantworten und Abgleichergebnissen |
| `backup_register` | Exportstände, tatsächliche Medienbestätigungen/Rückleseprüfungen und Wiederherstellungsergebnisse mit Ereignishistorie |
| `timestamp-status.json` | Technischer Verifikationscache, an genaue Nachweis-/OTS-Hashes gebunden; keine finanzielle Datenbank |
| `local_*_settings/events/workflow`, `imports` | Profile, Ablauf-/Änderungsinformationen und Importprovenienz |
| `bookkeeping_checklist.json` | Operative Abstimmung des privaten Workspaces |
| `export-manifest.json` | Zuordnung verschlüsselter Referenzen zu Originalexporten, Umfang und Kataloghash |
| `database.json`, `index.html` | Vereinfachte aktuelle Belegansicht; kein Ersatz für den Katalog |
| `nachweise/`, `migration/*.enc` | Zeitbeweise und versiegelte Migrationsnachweise |

Git-Objekte liegen nicht im Klartextexport. Vollständige Git-Historien sind über die CD-Sicherung wiederherstellbar. Für eine Prüfung werden geeignete Entschlüsselung, Datenbeschreibung und Auswertungsmöglichkeit bereitgestellt; Umfang, Zugriffsart und Übermittlung sind konkret abzustimmen. Keine behördliche Importschnittstelle wird behauptet.

CSV verwendet UTF-8, Semikolon, vollständig eingeschlossene Felder, doppelte Anführungszeichen als Escape und LF-Zeilenende. Dokumentnummern bleiben Text mit führenden Nullen. Fehlende Belegbeträge bleiben leer; sie werden nicht zu Null umgedeutet. Der vollständige Knotenexport enthält sämtliche Werte und Beziehungen, auch außerhalb der vereinfachten Belegtabelle. Geldbeträge in `records.csv` sind Dezimalwerte in Währungseinheiten; gemischte Steuergruppen bleiben zusätzlich im Katalog/Knotenexport. Der vollständige Original-/JSON-Export bleibt erhalten. Ein allgemeines PDF/A-Format ist keine pauschale GoBD-Voraussetzung; Originalformat und maschinelle Auswertbarkeit sind zu sichern. Der Beschreibungsstandard der Finanzverwaltung ist eine freiwillige Bereitstellungshilfe; diese CSV-/JSON-Dateien behaupten keine Umsetzung seines XML-Profils. [BMF: GoBD, Rz. 131–135, 176 und Anlage zur Datenüberlassung](https://ao.bundesfinanzministerium.de/ao/2026/Anhaenge/BMF-Schreiben-und-gleichlautende-Laendererlasse/Anhang-33/inhalt.html).

## 4. Betriebsdokumentation

### Kontrollen und Verantwortlichkeit

Der betriebliche Verantwortliche legt Quellen, Berechtigte, Eingangskontrolle, Erfassungsfristen und Vertretung in der privaten Ergänzung fest. Der Agent bereitet vor; er darf eine allgemeine Wartungsanweisung nicht als konkrete Rechnungs-/Ausgabenfreigabe behandeln. Der tägliche Verkaufsabgleich wird über den ausdrücklich eingerichteten Scheduler aufgerufen. Eingereichte Kostenbelege werden einzeln geprüft; kein automatischer Gebührenimport. Originalrechnungen und tatsächlich verfügbare Zahlungen sind anhand der jeweiligen Quellen zu prüfen. Fehlende Originale und unverarbeitete Vorgänge dokumentieren. Integritätsprüfung allein stellt keine Vollständigkeit fest.

Bei jedem Abschluss Prüfbasis und Freigabe festhalten, Pipelineergebnis lesen und Fehler beheben. Periodisch Vollständigkeit und Summen mit den außerhalb dieses Tools geführten übrigen Geschäftsvorfällen abgleichen. Die genaue Verantwortlichkeit, Häufigkeit, Ausnahmen und tatsächlichen Ergebnisse gehören in die private Betriebsdokumentation. Diese Anforderungen sind noch keine Bestätigung ihrer Durchführung.

### Aufbewahrung und Sicherung

Die betriebliche Vorgabe ist mindestens elf volle Kalenderjahre nach Ablauf des Jahres des letzten relevanten Vorgangs; spätere Zahlung/Korrektur kann den Horizont verlängern. `archiv retention` ist eine konservative Übersicht der erkannten Beleg-/Ereignisdaten; unbekannte Fristgrundlagen bleiben ungeklärt. Es gibt keinen automatischen Löschlauf oder Git-Garbage-Collection-Ablauf. Vor einem späteren Cut sind rechtliche Verlängerungen, Verfahren, Verknüpfungen und die Daten in Historien/Sicherungen gesondert zu prüfen.

Gesetzliche Fristen sind nach Unterlagenart unterschiedlich: Buchungsbelege grundsätzlich acht Jahre, Bücher/Aufzeichnungen grundsätzlich zehn, andere genannte Unterlagen sechs. Der Fristbeginn richtet sich nach der jeweiligen Unterlagenart; steuerlich noch relevante Unterlagen können länger erforderlich sein. Die Elfjahresvorgabe ist eine eigene Mindestpolitik, keine allgemeine gesetzliche Frist und keine automatische Löschfreigabe. [§ 147 AO](https://www.gesetze-im-internet.de/ao_1977/__147.html).

Monatlich `sicherung export --output NEUES_ZIEL` erzeugen. Es umfasst aktuellen verschlüsselten Bestand, Dokumentation, Wiederherstellungscode, vollständiges Toolbundle und zusätzlich verschlüsseltes Datenbundle einschließlich Migrationshistorie. `BACKUP.json` bezeichnet die gesicherten Daten-/Toolcommits; `SHA256SUMS.json` umfasst alle Paketdateien. Das geprüfte Paket wird anschließend mit Manifesthash, Exportpfad und Zeitpunkten im verschlüsselten `backup_register` registriert und separat veröffentlicht. Dieser Registereintrag entsteht nach dem Snapshot; er wird erst in folgenden Sicherungen enthalten sein. Ein unterbrochener Export kann mit `sicherung registrieren ORDNER` eingetragen werden. Bei offener Veröffentlichung zuerst `veroeffentlichen resume` verwenden.

Mit `sicherung pruefen ZIEL` Prüfsummen prüfen. Das Paket muss anschließend tatsächlich auf ein geeignetes Medium geschrieben, dieses abgeschlossen und zurückgelesen werden. `burned: false` bedeutet nur vorbereitet. Erst `sicherung bestaetigen --id ID --directory MEDIUM --medium KENNUNG --written --approved` liest alle Dateien des angegebenen Mediums gegen den registrierten Manifesthash und protokolliert die ausdrücklich bestätigte erfolgte Beschriftung/Finalisierung. Derselbe Exportordner als Rückleseziel wird abgelehnt. Der Helfer erkennt keine Brennerhardware; die tatsächliche Mediumart und das Schreiben/Abschließen bleiben menschliche Bestätigungen. Das Dashboard zeigt vorbereitete, bestätigte und zurückgelesene Sicherungen sowie den letzten Restoretest; nach 31 Tagen ohne bestätigte Rückleseprüfung zeigt es eine Erinnerung. Es löst keinen Brennvorgang aus. Passwort und benötigte Wiederherstellungsmittel getrennt sichern.

`sicherung test --id ID --directory MEDIUM` entschlüsselt das Datenbundle in einem neuen temporären Ordner außerhalb beider Repos, klont beide Git-Bundles, stellt die gesicherten Commitstände her, führt Git-Objektprüfung, Archiventschlüsselung, Originalhash-/Inventarprüfung und Prüfung der historischen Git-Nachweisdateien durch. Ergebnis und Umfang werden im Register erhalten; temporäre Klartextbundles werden anschließend entfernt. Das Passwort bleibt im Speicher und wird auch für die versiegelte Migrationshistorie direkt weitergereicht; keine temporäre `.env`-Kopie wird angelegt. Der Test verwendet die aktuelle Helferversion und vorhandene Python-Abhängigkeiten. Er prüft keine unabhängige Neuinstallation auf einem Ersatzrechner und verifiziert Bitcoin nicht erneut. Diese ergänzenden Tests bleiben betrieblich nötig; das CD-Paket enthält keinen vollständigen Offline-Paketspiegel. Fehlgeschlagene Wiederherstellung, Medienwechsel und durchgeführte Tests privat protokollieren. GitHub ist kein alleiniger unabhängiger Archivnachweis.

### Grenzen des Zeitnachweises und Änderungen

OTS belegt die Existenz des gehashten Commitnachweises spätestens am bestätigten Blockchain-Zeitpunkt. Es beweist weder Eingang/Zahlung noch richtige Steuerzuordnung oder Vollständigkeit. Ein später veränderter Commit kann nicht mit dem alten Beweis validiert werden; ein zerstörter alter Bestand ist dadurch aber nicht wiederhergestellt. Alte Nachweise, Git-Objekte und Medien weiter aufbewahren. Fremde Kalender erhalten Hashwerte, keine Belege.

`veroeffentlichen confirm` aktualisiert OTS-Dateien und prüft Bitcoin-Anker samt historischem Gitbezug über zwei öffentliche Blockquellen. Sein privater Verifikationscache bindet das Ergebnis an SHA256 der genauen Nachweis- und OTS-Datei. Das Dashboard zählt nur übereinstimmende gespeicherte Verifikationen als geprüft; geänderte Beweise werden nicht mit einem alten Cache bestätigt. Nachweis-/Cache-/Dashboardänderungen erhalten einen eigenen privaten Nachweisupdate-Commit ohne neue finanzielle Buchung und ohne rekursiv immer neue Zeitstempel zu erzeugen. Die öffentlichen Quellen ersetzen keinen unabhängig betriebenen Bitcoin-Vollknoten.

Toolupdates werden getestet und nur allgemein im öffentlichen Repo veröffentlicht. Der private Workspace dokumentiert die verwendete Toolrevision. Jede Funktionsänderung muss die öffentliche Verfahrensbeschreibung und erforderlichen privaten Betriebsangaben im selben Entwicklungsschritt prüfen und aktualisieren; organisatorische Unbekannte bleiben offen. Änderungen am Verfahren und organisatorische Abweichungen werden zusätzlich privat datiert und mit vorherigem Stand aufbewahrt. Vor Änderungen an Aufbewahrung, Export oder Rechnungsformaten vorhandene Originale und historische Nachweise verifizieren. Kein rückwirkendes Ersetzen empfangener PDFs durch selbst erzeugte XML.

### Release- und Zugriffskontrollen ab 0.1.0-beta.1

Einrichtung, schreibende Haupt-CLIs und der erzeugte Daten-Pre-Push-Hook prüfen die
tatsächliche GitHub-Sichtbarkeit über authentifizierte Metadatenabfrage. Erwartete
Adresse, `full_name`, `private: true` und `visibility: private` müssen übereinstimmen.
API-/Authentifizierungsfehler, fremde Netzwerkremotes und unbestätigte Umbenennungen
sperren die Veröffentlichung. Die Prüfung verwendet nur bereits vorhandene
Git-Credentials oder lokal konfigurierte Tokens mit lesendem Metadatenzugriff.
Einmalige Prüfung ist keine dauerhafte Zusicherung; zwischen Abfrage und Push ist
kein atomarer Sichtbarkeitsschutz möglich. GitHub-Berechtigungen und bewusstes
Umgehen von Hooks bleiben organisatorisch zu kontrollieren. Lokale Bare-Repos im
isolierten Entwicklungstest sind keine bestätigten privaten GitHub-Repos.

Versionen werden mit unveränderlichen Git-Tags und `CHANGELOG.md` beschrieben;
Python-Version und Gitrevision bleiben identifizierbar. Der Release-Test erzeugt
in einem separaten Klon zwei frische Pythonumgebungen für Installation und Restore,
mit ausschließlich synthetischen Buchungen und simulierter externer OTS-Antwort.
Quellen-/GitHub-/Bitcoin-Liveprüfungen sind davon getrennt. Das Testprotokoll erfasst
Paketversionen und Grenzen. Ein frisches Venv ist kein getesteter physischer
Ersatzrechner. Eigenständige Wiederherstellung des Nutzerbestands ist ein lesender
separater Test, keine neue Buchung; Durchführung nur bei tatsächlichem Ergebnis
privat dokumentieren. Die MIT-Lizenz eigenen Codes ersetzt nicht AGPL-/EUPL-Pflichten
der mitverwendeten Bibliotheken; `THIRD_PARTY_NOTICES.md` bleibt Teil der Sicherung.
