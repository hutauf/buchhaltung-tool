# Änderungen

## Unveröffentlicht

- DATEV ausschließlich per CLI: Dashboard erstellt den Befehl statt Downloads.
  Geschäftspartnernamen in EXTF-Buchungstext und Beleginformationen; vollständige
  Personenmetadaten, Historien und Originale aller Jahre im Begleitarchiv außerhalb
  beider Repos. Protokollierte Zeichen-/Feldanpassungen, vollständige Prüfsummen und
  kein fertiger Zielordner bei Abbruch. Verfahrensbeschreibung Version 12.
- DATEV-Leseexport per Dashboard und CLI: EXTF 700/13, CP1252/CRLF,
  echtes Empfängerprofil, SKR03-EÜR 2026, Zahlungen und Erstattungen ohne
  doppelte Erlöse, separater Homeoffice-Stapel. ZIP mit Begleitbericht und
  Prüfsummen; Ausnahmen sichtbar. Keine Archivänderung oder Zeitstempel.
  Eigenständiger Formatprüfer und Browser-/CLI-Vergleich; kein DATEV-Importtest.
  Verfahrensbeschreibung Version 11.


- Umfang auf einfache Kleinunternehmer-Aufzeichnungen beschränkt; Vorbereitung
  und Abschluss neuer eigener Rechnungen sperren Regelbesteuerung. EÜR-Vorschlag
  entsprechend reduziert, Produkttester-Leistungsumsätze ausgenommen. DATEV als
  möglicher gesonderter Exportadapter eingeordnet. Verfahrensbeschreibung Version 10.


- Dauerhafte eBay-Abweichungsvermerke mit Originalbezug, Wiederöffnung und
  anonymisierter Dashboard-Anzeige; Storno-/Ersatzketten gesondert sichtbar.
- Geführte private Betriebsdokumentation per Terminal oder Agenten-Prompt,
  prüfbare externe Entwürfe und verschlüsselte versionierte Speicherung.
- Jahresbericht mit Zahlungs-CSV und vollständigem Archivexport. Keine neue
  Zeitstempel-Einreichung für Leseexporte. EÜR-/DATEV-Zuordnung zunächst als Vorschlag.
- Neue formale Rechnungsberichtigungen auch als validierte EN16931-XML Typ 384.
  Originalbeträge bleiben erhalten; kein zusätzlicher Geldfluss. Verfahrensbeschreibung Version 9.


- Dashboard prüft das erinnerte Passwort jetzt tatsächlich offline: archivbezogener
  Salt, PBKDF2-HMAC-SHA256 mit 2.100.000 Iterationen, Fehlermeldung bei falscher
  Eingabe und 24-Stunden-Bestätigung ausschließlich nach Erfolg. Kein Passwort
  wird gespeichert oder übertragen; Überspringen bleibt möglich. Alte ungeprüfte
  Bestätigungen gelten nicht weiter. Verfahrensbeschreibung Version 8.

- Passwort-Einrichtung ist bereits vor dem ersten Datencommit möglich; das
  freigegebene private Ziel wird auch ohne vorhandenen Upstream geprüft.

- Manuelle Ersatzrechnungen nach vollständigem Storno bleiben explizit mit dem
  Original verknüpft und erzeugen keinen zusätzlichen Zahlungseingang.

- Geführte Beleg-, Zahlungs-, Korrektur- und Profilerfassung ohne selbst erstellte
  JSON-Dateien; manuelle Rechnungsentwürfe ohne externe Dienste. Vine optional,
  konfigurierte Fehler werden weiterhin gemeldet. Freigaben bleiben getrennt.
- Überspringbare Passwort-Prüfung im Browser, lokale verdeckte
  Schlüsselprüfung und Einrichtung mit unabhängiger Passwortsicherung.
- Sichere verständliche Fehlermeldungen, Hinweise zur Wiederaufnahme, passende
  Restore-Befehle je Sicherung und unverbindliche Sicherungsempfehlungen.
  Historische Nachweise und Jahresüberschuss inkl. Homeoffice klarer eingeordnet.
- Verfahrensbeschreibung Version 7 und Einrichtungs-/Wiederherstellungsanleitung
  beschreiben die neuen Abläufe und die tatsächlichen Grenzen.

- Erstkonfiguration mit betrieblicher Dokumentation lässt sich wieder vor der
  Archivinitialisierung committen. CI bewahrt auch bei fehlgeschlagenem
  Neueinrichtungs-/Wiederherstellungstest das synthetische Diagnoseprotokoll auf.

- Zwei ältere Datenschutz-Testvorlagen an den zusätzlichen Verfahrensplatzhalter
  angepasst; die strenge Dashboard- und Datenschutzprüfung bleibt erhalten.

- Verfahrensbeschreibung erläutert die kryptografische Absicherung bestätigter
  Archivstände auch gegenüber Administratoren: Git-/Dateiprüfsummen, zeitnahe
  OTS-Einreichung, externer Bitcoin-Anker und überprüfbare Fortschreibung.
  Erreichte Schutzwirkung und betriebliche Voraussetzungen sind getrennt beschrieben.

- Eigener Dashboard-Reiter „Verfahrensdoku“ mit vollständig eingebetteter
  allgemeiner Beschreibung, Inhaltsverzeichnis und Quellenprüfsumme. Die private
  betriebliche Ergänzung bleibt separat verlinkt; Dokumentation ist Bestandteil
  der deterministischen Dashboard- und Commit-Prüfung.

- Dashboard mit drei Arbeitsbereichen, klickbaren Monats-/Jahresgrafiken,
  Ausgabenkategorien, kumuliertem Einnahmenüberschuss und Bestandszusammenfassung.
  Erweiterte Filter, entfernbare Filterchips, Schnellansichten für Prüfbedarf und
  Stornos, sortierbare Belegspalten, variable Seitengröße und Kopierknöpfe für
  Belegaktionen; weiterhin eine einzelne vollständig offline nutzbare HTML-Datei.

- Offline-Dashboard prüft Aufbewahrungsfristen direkt in JavaScript zum aktuellen Tag in Europe/Berlin oder einem gewählten Stichtag. Anonymisierte Fristgruppen berücksichtigen den gesamten Archivbestand einschließlich späterer Zahlungen und Korrekturen; die CLI bleibt optional.

- Dashboard-Filter „Storno / Teilerstattung“ berücksichtigt auch stornierte und teilweise geminderte Originalrechnungen, einschließlich importierter Storno-Status.

- Große Datenveröffentlichungen übergeben Git-Dateipfade über Standardeingabe; dadurch bleibt der Git-Befehl unter der Windows-Befehlslängengrenze. Nur die ausgewählten Dateien werden aufgenommen.

- README auf Einstieg, Anbindungen und GoBD-Kontrollen mit Grenzen gekürzt.
- Ausführliche Referenz ins Handbuch verschoben; Zugänge und Rechnungsprofil separat erklärt, einschließlich der bestehenden Vine-Voraussetzung für eBay-Rechnungsentwürfe.

## 0.1.0-beta.1

Erste Testversion zum Klonen des Toolrepos mit unabhängigem privatem Datenrepo.

- Verschlüsseltes Belegarchiv, lokale Rechnungen und nachvollziehbare Korrekturen.
- Lieferanten-Minderungen mit Originalbezug und gesonderten Erstattungszahlungen.
- Vollständiger eBay-Verkaufsabruf im gewählten Fenster, ohne Gebührenimport.
- Offline-Dashboard mit kopierbaren CLI-Befehlen und Sicherungs-/Nachweisstatus.
- Sicherungsregister, Git-/OpenTimestamps-Pipeline und Wiederherstellungshelfer.
- Aktuelle Verfahrensbeschreibung und private betriebliche Ergänzung.
- Authentifizierte GitHub-Privatheitsprüfung vor Einrichtung, Buchung und Datenpush.
- Synthetischer Einrichtungs-/Wiederherstellungstest und Versionsausgabe.
- Lizenzhinweise für die vollständige Kombination einschließlich AGPL-Abhängigkeit.

Grenzen: einzelne EÜR-Einträge, keine abgabefertige EÜR; kein automatischer
Rechnungsversand, kein Gebührenimport, keine vollständige Sondersteuerabdeckung.
Nummernübergabe und konkrete Buchungen verlangen Freigabe. CD-Brennen bleibt manuell.
Rechnungs-XML ist EN16931-UBL, keine XRechnung-CIUS oder zertifiziertes ZUGFeRD-PDF.

## Versionsregeln

Git-Tags `vMAJOR.MINOR.PATCH` beziehungsweise `vMAJOR.MINOR.PATCH-beta.N` markieren
unveränderliche Releases. Beta-Versionen verwenden im Python-Projekt die passende
PEP-440-Schreibweise (`0.1.0b1`). Änderungen mit gleichem Umfang erhöhen PATCH;
neue Funktionen MINOR. Inkompatible Änderungen an Datenformat oder Ablauf erhalten
einen dokumentierten Migrationsweg und gesonderte Versions-/Freigabeentscheidung.
Während 0.x können noch inkompatible Änderungen auftreten; niemals einen
veröffentlichten Tag verschieben. Änderungen zunächst im Abschnitt Unveröffentlicht
dokumentieren. `tool-version.json` hält zusätzlich die exakte Gitrevision fest.
