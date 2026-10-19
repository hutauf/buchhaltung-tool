# Verfahrensdokumentation der lokalen Belegablage

Version 7 · Technikstand 19.10.2026, rechtliche Grundlagen zuletzt geprüft am 07.10.2026. Sicherheitsbeschreibung mit Implementierung und OpenTimestamps-Primärdokumentation am 19.10.2026 abgeglichen. Änderungen dieser Beschreibung werden mit der Toolhistorie versioniert. Die im privaten Workspace verwendete Toolrevision steht in `tool-version.json`.

## 1. Allgemeine Beschreibung

Dieses Werkzeug verbindet lokale Verkaufsrechnungen, Korrekturbelege und zugehörige Ausgaben zu einer nachvollziehbaren Belegablage. Originale bleiben verschlüsselt erhalten, Zahlungen und Korrekturen bleiben zugeordnet, und jede reguläre Datenveröffentlichung durchläuft Integritätsprüfung, Git-Versionierung und die Einreichung eines unabhängigen Bitcoin-Zeitnachweises. Diese aufeinander aufbauenden Kontrollen schaffen eine überprüfbare Grundlage für die betreuten EÜR-Einträge.

Der besondere Schutz liegt in der Verbindung von versionierter Historie und extern bestätigter Zeitbindung: Ein nachträglich umgeschriebener Bestand lässt sich nicht mit dem ursprünglichen Bitcoin-Nachweis als damaliger unveränderter Stand ausgeben. Die technische Sicherung wird durch konkrete Freigaben, Quellenabgleich und geprüfte Sicherungen ergänzt. Der derzeitige fachliche Umfang sind Verkäufe und zugehörige Ausgaben; weitere Unternehmensvorgänge, Vine-Entnahmen, Sondersteuern und eine vollständige EÜR werden gesondert abgedeckt oder später ergänzt.

Die GoBD verlangen für steuerrelevante elektronische Aufzeichnungen Nachvollziehbarkeit, Vollständigkeit, Richtigkeit, zeitgerechte Erfassung, Ordnung, unveränderbare beziehungsweise protokollierte Änderungen, Belegzuordnung, Kontrollen, Datensicherheit, Aufbewahrung, Lesbarkeit und Datenzugriff. Das betrifft auch einschlägige Aufzeichnungen bei EÜR; eine Bilanzierungspflicht ist dafür nicht Voraussetzung. Verantwortung bleibt beim Steuerpflichtigen. Eine Verfahrensbeschreibung umfasst allgemeine, Anwender-, technische und Betriebsdokumentation; Softwaretestate binden die Finanzverwaltung nicht. [BMF: GoBD-Grundtext, insbesondere Abschnitte 1–3, 6–11 und 12](https://usth.bundesfinanzministerium.de/ao/2026/Anhaenge/BMF-Schreiben-und-gleichlautende-Laendererlasse/Anhang-33/inhalt.html).

Diese Beschreibung ordnet die vorhandenen Kontrollen den GoBD-Anforderungen zu und erläutert ihre Prüfung. Die [betriebliche Ergänzung](betriebliche-ergaenzung-vorlage.md) hält die tatsächlichen Verantwortlichkeiten, Quellen und durchgeführten Kontrollen im privaten Datenrepo fest. Technische Absicherung und dokumentierter Betrieb bilden zusammen das Verfahren.

| Anforderung | Mechanismus dieses Workflows | Beitrag zum ordnungsgemäßen Betrieb |
|---|---|---|
| Nachprüfbarkeit | Originalhash, Beleg-ID, Referenzen, Metadatenhistorie, Quell-/Prüfbasis | Vorgänge bleiben vom Original über Verarbeitung und Korrektur bis zur Auswertung verfolgbar |
| Vollständigkeit | Alle archivierten Originale und Versionen erhalten; Export ohne Jahresverlust; gespeicherter eBay-Verkaufsabgleich | Der Archivbestand ist vollständig exportierbar; der Quellenabgleich ergänzt ihn im festgelegten API-Zeitfenster. Übrige Unternehmensquellen werden betrieblich einbezogen |
| Richtigkeit | Summen, Steuergruppen, Dubletten und freigegebene Revision prüfen; XML lokal validieren | Technische Prüfungen sichern die Verarbeitung; betrieblicher Bezug und Sondersteuern werden anhand der Quellen freigegeben |
| Zeitgerechte Erfassung | Vorbereitung und Abschluss getrennt, Datum und Ereignisse erfasst | Eingangskontrolle und Erfassungstakt privat verbindlich festlegen |
| Ordnung/Belegfunktion | Jahr, Dokumentart, eindeutiger Kontext, Verknüpfung zu Zahlungen/Korrekturen | Belege bleiben eindeutig auffindbar und zugeordnet; fehlende Originale werden zur Nachbearbeitung ausgewiesen |
| Unveränderbarkeit | Erhaltene Originale, verkettetes Änderungsprotokoll, Git-Historie und extern bestätigte Bitcoin-Zeitnachweise je Datenveröffentlichung | Bestätigte Archivstände sind kryptografisch gegen unbemerkte nachträgliche Ersetzung abgesichert. Neue Nachweise ersetzen keinen früheren Existenzbeweis; Nachweiskopien und Sicherungen sichern dessen Erhalt |
| Internes Kontrollsystem | Freigaberevisionen, Rückleseprüfung, Integritätsprüfung und gespeicherter technischer Kontrollnachweis vor Datenveröffentlichung | Technische Kontrollen werden automatisch ausgeführt und dokumentiert; Quellenabgleich und betriebliche Fehlerbehandlung ergänzen sie |
| Datensicherheit | Verschlüsselung und Trennung von Code/Daten, keine Klartextoriginale in Git | Passwort-/Zugriffsverwaltung, Datenträger und Wiederherstellung privat festlegen |
| Aufbewahrung | Elfjährige Mindestpolitik, keine automatische Löschung, Originalformate erhalten | Verlängerungen prüfen; Fristprüfung allein erlaubt keine Löschung |
| Lesbarkeit/Auswertbarkeit | Entschlüsselung außerhalb, vollständiger JSON-/CSV-Katalog, Feldtypen/Verknüpfungen, XML-/PDF-Originale und Belegansicht | Prüfexport und erforderliche Auswertungen mit Prüfer abstimmen; kein zugesicherter IDEA-Import |
| Systemwechsel | Beide Git-Bundles, Archiv und versiegelte Migrationshistorie in CD-Export; isolierter Restoretest im Register | Neuinstallation der Abhängigkeiten und Blockchainprüfung separat erproben; Quellenvollständigkeit vor Übergabe prüfen |
| Verfahrensdokumentation | Diese vierteilige Beschreibung, private Ergänzung und Versionshistorie | Betriebsangaben und durchgeführte Kontrollen dürfen nicht durch Vorlagen ersetzt werden |

## 2. Anwenderdokumentation

Einrichtung und Zugangskonfiguration stehen in der [Einrichtungsanleitung](einrichtung.md); die vollständige Befehlsreferenz im [Handbuch](handbuch.md). Die README fasst Einstieg, GoBD-Kontrollen und Grenzen zusammen. Diese redaktionelle Aufteilung ändert das Verfahren nicht. Vine ist optional; eine nicht konfigurierte Bestandsprüfung wird so protokolliert, eine fehlerhafte konfigurierte Anbindung dagegen nicht übergangen. Manuelle Rechnungen benötigen keine externe Anbindung und folgen derselben Nummern-, Freigabe-, Archiv- und Nachweispipeline.

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

Die ausgewählten Commit-Dateipfade werden als unveränderte, nullgetrennte Liste über die Standardeingabe an Git übergeben. Damit lassen sich auch umfangreiche Erstimporte unter Windows veröffentlichen, ohne die Befehlslängengrenze zu überschreiten; andere Dateien werden weiterhin nicht aufgenommen. Ein dienstunabhängiger öffentlicher Batch-Importbefehl ist noch nicht vorhanden.

Das Dashboard enthält eine fest begrenzte Projektion ohne Käufer, Anschriften oder Artikeltexte. Es ist eine Übersicht erfasster einzelner EÜR-Einträge. Zahlungen, Belegbeträge und Pauschalen sind getrennt. Beleg-/Zahlungsstichtage und Sonderzuordnungen sind mit den übrigen Unternehmensaufzeichnungen zusammenzuführen. CSV aus dem Dashboard ist ein Arbeitsbericht, kein vollständiger Prüfexport.

Der Belegart-Filter „Storno / Teilerstattung“ zeigt separate Minderungsbelege sowie stornierte oder teilweise geminderte Originalrechnungen. Ein importierter Storno-Status bleibt an der Originalrechnung erhalten; der Filter erzeugt daraus keinen neuen Stornobeleg und keine Rückzahlung. „Prüfung → Storniert“ grenzt auf stornierte Originalrechnungen ein. Jahres-, Such- und übrige Filter gelten weiterhin; „Alle Jahre“ zeigt auch historische Vorgänge.

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

Vorhandene Archive ohne `audit_trail` bleiben lesbar. Bei der nächsten Katalogänderung wird ihr Ausgangsbestand als `existing_state` erhalten. Frühere Eingangstermine oder Kontrollhandlungen werden nicht rückwirkend behauptet. Die Protokollzeit belegt die lokale Verarbeitung, nicht automatisch den früheren E-Mail-Eingang. Separat gespeicherte Checklistenänderungen bleiben über die verschlüsselte Datei und Git-Historie prüfbar; sie sind keine Katalogänderungsereignisse. Für Zugriffe außerhalb der Helfer ergänzt die externe Zeitverankerung die Anwendungskontrollen: Auch mit Administratorrechten kann ein veränderter Stand den alten Existenzbeweis nicht übernehmen. Unabhängige Nachweiskopien und Sicherungen erhalten die Vergleichsgrundlage.

Vor einem neuen Datencommit speichert die Veröffentlichung unter `processing_controls` einmalig je Pipelinekennung die tatsächlich bestandene Archiv-Integritätsprüfung mit Datum, Toolrevision, geprüftem Kataloghash und Beleg-/Dokumentanzahl. Auch dieser Nachweis wird verschlüsselt, protokolliert und im Datencommit verankert. Er behauptet ausdrücklich keinen vollständigen Quellenabgleich. Unveränderte Leseprüfungen und reine OTS-Nachweiscommits verändern den Katalog nicht. Fehler bleiben über Pipeline-/Transaktionszustand sichtbar; deren Ursachen und Behebung sind zusätzlich betrieblich nachzuweisen. Quellenabgleich und Wiederherstellungstests sind weiterhin durchzuführen und separat zu dokumentieren. [BMF: GoBD, Rz. 59–60, 88, 100, 107–117](https://ao.bundesfinanzministerium.de/ao/2026/Anhaenge/BMF-Schreiben-und-gleichlautende-Laendererlasse/Anhang-33/inhalt.html).

Die zentrale Schreibfunktion erlaubt bei Originaldateien ausschließlich das erneute Schreiben identischer Bytes. Der Kataloghelfer erhält vorhandene Dokumentreferenzen, Originalhashes und Größen. Korrekturen bekommen neue Originale und bleiben verknüpft. Damit werden Originalerhalt und nachvollziehbare Fortschreibung bereits beim regulären Schreiben durchgesetzt; die Git-/Bitcoin-Nachweiskette sichert die bestätigten Stände zusätzlich gegen unbemerkte rückwirkende Ersetzung ab.

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

Die allgemeine Verfahrensbeschreibung wird bei jeder Dashboard-Erzeugung vollständig
in den Reiter „Verfahrensdoku“ eingebettet, mit Inhaltsverzeichnis, Versionsangabe
und SHA-256 der Quelldatei. Sie ist auch ohne Toolordner oder Internet lesbar.
Der Commit-Hook berücksichtigt die Dokumentation als Generatorquelle und prüft
den zum Commit passenden Stand; nicht vorgemerkte Quellenänderungen werden
abgewiesen. Die private betriebliche Ergänzung wird separat verlinkt, ihr Inhalt
aber nicht ins anonymisierte HTML übernommen. Der Link öffnet den lokalen
Dateistand, keinen eingebetteten historischen Snapshot. Bei fehlender Ergänzung
zeigt das Dashboard den offenen Einrichtungsbedarf. Die bloße Existenz der Datei
belegt weder ausgefüllte Verantwortlichkeiten noch durchgeführte Kontrollen.
Externe Rechtsquellen werden als Links dargestellt und nicht automatisch geladen.

Das statische Dashboard trennt Übersicht, Belegverzeichnis und Kontrollen/Änderungen.
Es verarbeitet ausschließlich die bereits erlaubten anonymisierten Snapshotfelder
im Browser, ohne Netzabruf, Personen-/Produktdaten oder Originalpfade.
Jahres-/Monatsfilter begrenzen Geldbewegungen nach Zahlungsdatum; zugehörige Belege
werden auch bei abweichendem Belegjahr einbezogen. Weitere Filter grenzen den
Belegbestand ein. Belegdatums- und Bruttobetragsgrenzen beziehen sich ausdrücklich
auf Belege, nicht auf Zahlungsdaten/-beträge. Verlauf, Ausgabenkategorien,
Zahlungskennzahlen und Beleg-CSV verwenden dieselbe Auswahl; die CSV umfasst alle
Seiten in der angezeigten Sortierung. Unbekannte Beträge bleiben unbekannt und
werden zuletzt sortiert. Stornierte Originale behalten ihre Belegart und Nummer;
eine Minderung wird nicht als tatsächlich erfolgte Rückzahlung ausgelegt.
Die Dashboard-Bezeichnung „Einnahmenüberschuss“ meint die Differenz der erfassten
Ein- und Auszahlungen; sie ist keine vollständige steuerliche EÜR. Die separat
ausgewiesene Homeoffice-Pauschale ist darin nicht enthalten.
Die kumulierte Zahlungslinie ist kein Bankkontostand. Die Jahresauswertung samt
Homeoffice berücksichtigt das ganze gewählte Jahr unabhängig von den übrigen
Filtern; Archivkontrollen den vollständigen Snapshot. Filter, Grafikklicks,
Kopierknöpfe und Vorschauen sind reine Anzeigeaktionen. Sie erzeugen keine Buchung,
Freigabe, Kontrolle im Archiv oder neuen Bitcoin-Nachweis. Tatsächliche Änderungen
erfolgen weiterhin mit geprüften CLI-Befehlen und deren Veröffentlichungsprozess.
Neue Daten erfordern die erneute Erzeugung des Dashboards.

Der betriebliche Verantwortliche legt Quellen, Berechtigte, Eingangskontrolle, Erfassungsfristen und Vertretung in der privaten Ergänzung fest. Der Agent bereitet vor; er darf eine allgemeine Wartungsanweisung nicht als konkrete Rechnungs-/Ausgabenfreigabe behandeln. Der tägliche Verkaufsabgleich wird über den ausdrücklich eingerichteten Scheduler aufgerufen. Eingereichte Kostenbelege werden einzeln geprüft; kein automatischer Gebührenimport. Originalrechnungen und tatsächlich verfügbare Zahlungen sind anhand der jeweiligen Quellen zu prüfen. Fehlende Originale und unverarbeitete Vorgänge dokumentieren. Integritätsprüfung allein stellt keine Vollständigkeit fest.

Bei jedem Abschluss Prüfbasis und Freigabe festhalten, Pipelineergebnis lesen und Fehler beheben. Periodisch Vollständigkeit und Summen mit den außerhalb dieses Tools geführten übrigen Geschäftsvorfällen abgleichen. Die genaue Verantwortlichkeit, Häufigkeit, Ausnahmen und tatsächlichen Ergebnisse gehören in die private Betriebsdokumentation. Diese Anforderungen sind noch keine Bestätigung ihrer Durchführung.

### Aufbewahrung und Sicherung

Die betriebliche Vorgabe ist mindestens elf volle Kalenderjahre nach Ablauf des Jahres des letzten relevanten Vorgangs; spätere Zahlung/Korrektur kann den Horizont verlängern. `archiv retention` ist eine konservative Übersicht der erkannten Beleg-/Ereignisdaten; unbekannte Fristgrundlagen bleiben ungeklärt. Es gibt keinen automatischen Löschlauf oder Git-Garbage-Collection-Ablauf. Vor einem späteren Cut sind rechtliche Verlängerungen, Verfahren, Verknüpfungen und die Daten in Historien/Sicherungen gesondert zu prüfen.

Das Offline-Dashboard enthält zusätzlich ausschließlich Fristdaten und Dateizählungen aus derselben Berechnung für den vollständigen Katalog, einschließlich Historien und verknüpfter Zahlungen/Korrekturen. Beim Öffnen vergleicht JavaScript diese Gruppen mit dem aktuellen Kalendertag in Europe/Berlin. Ein anderer Prüfstichtag kann direkt in der HTML-Datei gewählt werden; er verändert nur die Ansicht. Jahres- und Belegfilter begrenzen diese Archivprüfung nicht. Unbekannte Fristgrundlagen bleiben ausdrücklich ungeklärt; ein erreichter Prüfhorizont ist keine Löschfreigabe. Neue Archivereignisse erfordern einen neu erzeugten Dashboard-Snapshot, während der Tagesvergleich auch ohne CLI aktuell erfolgt. Die CLI bleibt für maschinelle Auswertung und gesonderte Prüfprotokolle verfügbar. Die Browseranzeige speichert keine Kontrolle im Archiv und belegt keine tatsächlich ausgeführte rechtliche Fristprüfung.

Gesetzliche Fristen sind nach Unterlagenart unterschiedlich: Buchungsbelege grundsätzlich acht Jahre, Bücher/Aufzeichnungen grundsätzlich zehn, andere genannte Unterlagen sechs. Der Fristbeginn richtet sich nach der jeweiligen Unterlagenart; steuerlich noch relevante Unterlagen können länger erforderlich sein. Die Elfjahresvorgabe ist eine eigene Mindestpolitik, keine allgemeine gesetzliche Frist und keine automatische Löschfreigabe. [§ 147 AO](https://www.gesetze-im-internet.de/ao_1977/__147.html).

Empfohlen ist ein monatlicher Export mit `sicherung export --output NEUES_ZIEL`. Die konkrete unabhängige Sicherungsstrategie und das Medium werden betrieblich festgelegt; eine CD wird vom Werkzeug nicht verlangt. Fehlende Medienbestätigung oder Restoretests bleiben sichtbar, sperren aber keine Buchung. Es umfasst aktuellen verschlüsselten Bestand, Dokumentation, Wiederherstellungscode, vollständiges Toolbundle und zusätzlich verschlüsseltes Datenbundle einschließlich Migrationshistorie. `BACKUP.json` bezeichnet die gesicherten Daten-/Toolcommits; `SHA256SUMS.json` umfasst alle Paketdateien. Das geprüfte Paket wird anschließend mit Manifesthash, Exportpfad und Zeitpunkten im verschlüsselten `backup_register` registriert und separat veröffentlicht. Dieser Registereintrag entsteht nach dem Snapshot; er wird erst in folgenden Sicherungen enthalten sein. Ein unterbrochener Export kann mit `sicherung registrieren ORDNER` eingetragen werden. Bei offener Veröffentlichung zuerst `veroeffentlichen resume` verwenden.

Mit `sicherung pruefen ZIEL` Prüfsummen prüfen. Soll der Export als unabhängig gesichertes und zurückgelesenes Medium registriert werden, muss er tatsächlich darauf geschrieben, abgeschlossen und zurückgelesen werden. Ein nur vorbereiteter Export wird nicht als durchgeführte Sicherung ausgegeben. `burned: false` bedeutet nur vorbereitet. Erst `sicherung bestaetigen --id ID --directory MEDIUM --medium KENNUNG --written --approved` liest alle Dateien des angegebenen Mediums gegen den registrierten Manifesthash und protokolliert die ausdrücklich bestätigte erfolgte Beschriftung/Finalisierung. Derselbe Exportordner als Rückleseziel wird abgelehnt. Der Helfer erkennt keine Brennerhardware; die tatsächliche Mediumart und das Schreiben/Abschließen bleiben menschliche Bestätigungen. Das Dashboard zeigt vorbereitete, bestätigte und zurückgelesene Sicherungen sowie den letzten Restoretest; nach 31 Tagen ohne bestätigte Rückleseprüfung zeigt es eine Erinnerung. Es löst keinen Brennvorgang aus. Passwort und benötigte Wiederherstellungsmittel getrennt sichern.

`sicherung test --id ID --directory MEDIUM` entschlüsselt das Datenbundle in einem neuen temporären Ordner außerhalb beider Repos, klont beide Git-Bundles, stellt die gesicherten Commitstände her, führt Git-Objektprüfung, Archiventschlüsselung, Originalhash-/Inventarprüfung und Prüfung der historischen Git-Nachweisdateien durch. Ergebnis und Umfang werden im Register erhalten; temporäre Klartextbundles werden anschließend entfernt. Das Passwort bleibt im Speicher und wird auch für die versiegelte Migrationshistorie direkt weitergereicht; keine temporäre `.env`-Kopie wird angelegt. Der Test verwendet die aktuelle Helferversion und vorhandene Python-Abhängigkeiten. Er prüft keine unabhängige Neuinstallation auf einem Ersatzrechner und verifiziert Bitcoin nicht erneut. Diese ergänzenden Tests bleiben betrieblich nötig; das CD-Paket enthält keinen vollständigen Offline-Paketspiegel. Fehlgeschlagene Wiederherstellung, Medienwechsel und durchgeführte Tests privat protokollieren. GitHub ist kein alleiniger unabhängiger Archivnachweis.

### Kryptografische Unveränderbarkeit durch Git und Bitcoin-Zeitnachweise

Die Absicherung besteht aus einer durchgehenden Nachweiskette: Originaldateien und verschlüsselte Metadaten werden durch ihre Prüfsummen identifiziert, der Git-Datencommit hält den zugehörigen versionierten Stand fest, und eine Nachweisdatei bindet diesen Stand an OpenTimestamps. Die Nachweisdatei enthält die konkrete Git-Commitkennung, zusätzlich SHA-256 des vollständigen Commitobjekts und SHA-256-Prüfsummen der einbezogenen Archivdateien. Damit hängt die Prüfung nicht allein an einer frei änderbaren Datumsangabe oder einer Versionsbezeichnung.

Jede reguläre Datenveröffentlichung prüft das Archiv, erzeugt und pusht den Datencommit und reicht anschließend dessen Nachweis bei OpenTimestamps ein. Der OTS-Nachweis wird separat versioniert und gepusht. Diese unmittelbare Einreichung pro Datenveröffentlichung sorgt im vorgesehenen Workflow für zeitliche Nähe zwischen Verarbeitung und externer Verankerung. Offene Veröffentlichungen bleiben als wiederaufnehmbare Vorgänge sichtbar. Die spätere Bitcoin-Bestätigung und ihre Prüfung werden gesondert ausgewiesen; Softwareänderungen und bloße Anzeigeaktualisierungen erzeugen keine neuen Buchhaltungszeitstempel.

**Schutz auch gegenüber Administratoren:** Wird ein bereits verankerter Bestand nachträglich umgeschrieben, passen die geänderten Dateiprüfsummen beziehungsweise das geänderte Commitobjekt nicht mehr zum damaligen Nachweis. Der alte OTS-Beweis bleibt für den ursprünglichen Stand gültig und kann für den abweichenden Stand nicht erfolgreich verwendet werden. Auch eine vollständige Neuberechnung lokaler Git-Historie, Protokolle und Prüfsummen verschafft dem veränderten Bestand diesen früheren Bitcoin-Anker nicht. Ein neu eingeholter Nachweis besitzt einen späteren Verankerungszeitpunkt und liefert keinen Existenzbeweis für den früheren Zeitpunkt. Ein zurückdatiertes Beleg- oder Git-Commitdatum ändert daran nichts. Geprüft wird jeweils der konkret bescheinigte Datencommit; ein gültiger Nachweis für einen anderen historischen Commit bescheinigt nicht automatisch den aktuellen Arbeitsstand.

**Erreichte Schutzwirkung:** Für bestätigte und überprüfte Archivstände besteht damit eine kryptografisch nachprüfbare Absicherung gegen unbemerkte nachträgliche Inhaltsänderungen. Die Blockchain-Verankerung liegt außerhalb der lokalen Administratorrechte. Sie ergänzt die Schreibkontrollen und Änderungsprotokolle um einen unabhängigen Existenznachweis des damaligen Datenstands. Die Nachweiskette lässt spätere Korrekturen als neue, verknüpfte Stände zu, während der ursprüngliche bestätigte Stand weiterhin überprüfbar bleibt. Das ist der zentrale technische Beitrag dieses Verfahrens zur Unveränderbarkeit und Nachvollziehbarkeit. [OpenTimestamps: Funktionsweise](https://opentimestamps.org/) und [Client: Erstellung und Verifikation](https://github.com/opentimestamps/opentimestamps-client/blob/master/README.md).

### Voraussetzungen, Aufbewahrung und verbleibende Grenzen

Die Schutzwirkung setzt einen bestätigten Bitcoin-Anker, die Prüfung der genauen Nachweisdatei und den Erhalt des zugehörigen historischen Datenstands voraus. Eine reine Kalenderannahme wird bis zur Bitcoin-Verifikation als ausstehend behandelt. Bei verzögerter oder unterbrochener Einreichung bleibt der neue Stand bis zur Verankerung noch ohne diesen externen Nachweis; der Veröffentlichungs-/Nachweisstatus dient der Nachbearbeitung. Eine feste maximale Bestätigungsdauer oder ein lückenloser zeitbasierter Hintergrundlauf wird derzeit nicht technisch erzwungen. Bei später importierten Altbelegen belegt der Anker den damaligen Archivstand, nicht rückwirkend deren ursprüngliches Ausstellungsdatum.

Die gespeicherten Dateien liegen auf gewöhnlichen Datenträgern und können mit ausreichenden Rechten technisch verändert oder gelöscht werden. Die Hash-/Zeitnachweiskette verhindert, dass ein abweichender Stand den erhaltenen alten Nachweis besteht; Sicherungen schützen zusätzlich vor Verlust und ermöglichen den Vergleich mit älteren Ständen. Deshalb werden Nachweisdateien, OTS-Beweise und historische Git-Objekte zusammen mit den Daten aufbewahrt und unabhängig gesichert. Integritätssicherung und Wiederherstellbarkeit ergänzen sich. Der Existenznachweis bestätigt den gesicherten Inhalt; fachliche Richtigkeit, Zahlung, fristgerechte Erfassung und Quellenabgleich werden durch die übrigen Kontrollen geprüft. Kalender erhalten Hashwerte, keine Belege.

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

## 5. Geführte Erfassung und Passwort-Erinnerung (Version 7)

`beleg neu PFAD` liest das Original und führt durch die Metadaten, einschließlich Steuergruppen, Zahlungsnachweis und Lieferanten-Korrektur. Ein strukturiertes XML wird nach Validierung vorbefüllt. Geprüfte Angaben werden nur als verschlüsselter Entwurf gespeichert; die konkrete Buchungsfreigabe bleibt ein eigener Schritt. Zahlungen, Stornos, Teilminderungen, formale Berichtigungen und Absenderprofil sind ebenfalls ohne selbst erstelltes JSON im Terminal erfassbar. Originalbezug, Quellenprüfung, Revisions-/Snapshotbindung und Dublettenprüfungen bleiben bestehen. Bei Zahlungszuordnungen wird ausdrücklich erklärt, dass manuell bestätigte Zahlungen die importierte Zahlungsquelle des Belegs ersetzen.

Manuelle Rechnungsentwürfe protokollieren eigene Auftragsreferenz und Prüfgrundlage; Name, Anschrift, Positionen, Steuerzuordnung und Leistungsdatum werden geprüft. Die Referenz dient der Dublettenprüfung und ist keine Rechnungsnummer. Ausstellen benötigt weiterhin Produktivfreigabe, konkrete Revision und fortlaufende Nummer. Eine manuelle Rechnung erzeugt keine behauptete eBay-Zahlung: Zahlung wird erst anhand eines tatsächlichen Nachweises separat zugeordnet. PDF und validierte EN16931-XML werden wie beim eBay-Weg archiviert.

Das Dashboard zeigt historische Bitcoin-Nachweiszahlen ausdrücklich als solche. Ausstehende neue Bestätigungen sind ein normaler Zwischenzustand und keine Buchungssperre; sie werden nicht als bestätigter Zeitbeweis ausgegeben. Der tatsächliche Publikationsstatus ist mit `veroeffentlichen status` lesbar. Bei einem Abbruch können Archivdaten bereits gespeichert sein: `veroeffentlichen resume` setzt dieselbe Transaktion fort, statt nochmals zu buchen. Die statische HTML-Datei kann einen späteren Netzwerk-/Pushfehler nicht live feststellen. Fehlermeldungen benennen sichere Fehlerkategorien und nächste Schritte, ohne HTTP-Antwortkörper oder Zugangswerte auszugeben.

Die freiwillige Passwort-Erinnerung im Dashboard ist kein Zugriffsschutz und keine Passwortprüfung. Ihre Eingabe wird sofort verworfen, nicht gespeichert und nicht übertragen. Es wird weder ein Passwort noch ein zusätzlicher Passwort-Prüfwert im HTML abgelegt. Nur der Erinnerungszeitpunkt kann 24 Stunden im lokalen Browserspeicher liegen; der Dialog bleibt überspringbar. `passwort pruefen` prüft eine verdeckte lokale Eingabe am tatsächlichen Datenschlüssel. Neue Passwörter werden mit mindestens 16 Zeichen und Bestätigung der getrennten Sicherung eingerichtet. Bestehende Archive bleiben auch mit älteren Passwörtern lesbar. Passwort, Rechnerzugang und unabhängige Notfallkopie müssen betrieblich verwaltet werden; ein Verlust des Passworts lässt sich nicht durch Git oder Bitcoin beheben. Passwort nicht bloß in der `.env` ersetzen; ein Rotationshelfer ist nicht vorhanden. Wiederherstellungshinweise erklären die lokale Passwortdatei explizit.

Nach vollständigem Storno sind verknüpfte manuelle Ersatzrechnungen über dieselbe Auftragsreferenz und expliziten Originalbezug möglich. Die alte Nummer bleibt erhalten, die Ersatzrechnung verwendet die nächste freigegebene Nummer. Zahlungen werden weiterhin separat zugeordnet.
