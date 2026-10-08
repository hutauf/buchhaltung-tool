# Änderungen

## Unveröffentlicht

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
