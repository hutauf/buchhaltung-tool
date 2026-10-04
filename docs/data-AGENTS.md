# Persönlicher Buchhaltungsworkspace

- Die unabhängige private Git-Wurzel ist dieser Ordner. Helfer liegen im übergeordneten Toolrepo unter `scripts/`; alle CLI-Befehle von dort ausführen.
- Belege und Personenmetadaten ausschließlich verschlüsselt archivieren. `.env` und entschlüsselte Dateien nie committen. Ansichten und Prüfkopien außerhalb beider Repos erstellen.
- Vor Anlage Quelle, Beleg, verschlüsselte Datenbank und `bookkeeping_checklist.json.enc` auf vorhandene Vorgänge und Dubletten prüfen. eBay-SRN und Order-ID-Aliase berücksichtigen.
- Entwürfe getrennt von Abschlüssen behandeln. Keine Rechnung ausstellen, Ausgabe buchen, Zahlung erfassen oder externe Buchung ändern, bevor der Nutzer die konkreten Daten freigegeben hat. Eine Migration ist keine solche Buchungsfreigabe. Kundenkommunikation benötigt eine eigene Freigabe.
- Vor Produktivbetrieb Nummernstand mit dem bisherigen Dienst vollständig abstimmen. Bis dahin lokale Rechnungen im Probebetrieb belassen.
- Für Importe den Belegimport-Skill des äußeren Toolrepos nutzen. Belegdatum und Zahlungsdatum unterscheiden; unbekannte Beträge, Steuerwerte und Zahlungen nicht erfinden.
- Originalbelege und endgültige Nummern erhalten. Korrekturen, Stornos und Zahlungsberichtigungen mit den vorhandenen verknüpften Folgebelegen und nachvollziehbaren Ereignissen erfassen.
- Die schreibenden lokalen Helfer prüfen und veröffentlichen automatisch Datencommit/Push und separaten OTS-Nachweis. Bei Abbruch `publish_bookkeeping.py resume` verwenden, niemals dieselbe Buchung wiederholen. OTS-Einreichung ist zunächst keine Bitcoin-Bestätigung.
- Im äußeren Toolrepo keine Buchhaltungscommits ausführen. Fremde Änderungen nicht zurücksetzen. Vor CD-Sicherung Bestände prüfen; eine erzeugte Sicherung ist noch keine gebrannte CD.
