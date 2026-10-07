# Private Ergänzung zur Verfahrensdokumentation

Diese Vorlage im **privaten Datenrepo** führen. Persönliche Angaben und konkrete Geschäftsvorfälle dürfen nicht ins öffentliche Toolrepo. Noch offene Angaben sind als offen zu markieren; keine durchgeführten Kontrollen behaupten. Bei sensiblen Details einen verschlüsselt archivierten Nachweis referenzieren.

| Betriebsangabe | Privat auszufüllen |
|---|---|
| Verantwortlicher, Vertretung, Freigabeberechtigte | Offen |
| Tatsächlich verwendete Quellen, betrieblicher Umfang und weitere Systeme für übrige EÜR-Positionen | Offen |
| Beginn des Verfahrens, Nummernübergabe, verwendete Toolrevision | Offen |
| Eingangskontrolle und Zeitpunkt der Sicherung/Erfassung | Offen |
| Verkaufsabgleich per API und Abgrenzung zu Bank/übriger EÜR | Täglichen Aufruf `abgleich ebay --days 90 --save` ausdrücklich einrichten; Zuständigkeit und Ausfallbehandlung offen. Kein automatischer Gebührenimport. Kosten nur aus eingereichten Belegen. Bankabgleich gesondert. |
| Prüfung von Original, XML, Steuern, Nutzung und Zahlungsnachweis | Zuständigkeit und Prüfnachweise offen |
| Behandlung fehlender Belege, Sondersteuern, Privatanteile, Ausnahmen | Offen |
| Zugriffsberechtigung, Geräte-/Datenträgerschutz, private Repo-Einstellungen | Offen |
| Passwortsicherung, Wiederherstellungsvertretung und getrennte Lagerorte | Offen; niemals Passwort selbst eintragen |
| Elfjährige Mindestaufbewahrung und mögliche Verlängerungen | Frist-/Verfahrensprüfung und zuständige Person offen |
| Monatssicherung, Medieninventar, Brennen/Finalisierung/Rücklesen | `backup_register` verwenden; erst nach realem Schreiben/Abschließen vom tatsächlichen Medium bestätigen. Medium, Lagerort und tatsächliche Ergebnisse offen. |
| Regelmäßiger Wiederherstellungstest einschließlich Abhängigkeiten | `sicherung test` im Register dokumentiert; unabhängige Neuinstallation und Bitcoin-Verifikation zusätzlich nötig. Testintervall und reale Ergebnisse offen. |
| Prüferzugriff und Exportfreigabe | Zuständigkeit und Vorgehen offen |

Kontroll-/Änderungsprotokoll je Eintrag: Datum, verantwortliche Person, geprüfter Zeitraum/Umfang, Methode, Ergebnis, Abweichung, Maßnahme und Referenz auf den archivierten Nachweis. Änderungen versionieren; frühere gültige Beschreibungen erhalten. Eine ausgefüllte Tabelle ersetzt nicht die tatsächliche Durchführung.
