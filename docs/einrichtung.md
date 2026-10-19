# Einrichtung und Anbindungen

Die [README](../README.md) enthält die Installationsbefehle für einen neuen Windows-Workspace. Hier stehen Zugangsdaten, Rechnungsprofil und Hinweise für bestehende Installationen. Alle Buchhaltungsbefehle im äußeren Toolordner starten.

Wenn Windows den Befehl `py` nicht kennt, `python -m venv .venv` verwenden. Ist auch `python` nicht im Suchpfad, den vollständigen Pfad zum installierten Python-Interpreter verwenden; Python 3.11 oder neuer bleibt erforderlich.

## GitHub-Zugang

Ein leeres **privates** Datenrepo anlegen, ohne vorab README oder andere Dateien hinzuzufügen. `setup_workspace.py` klont es unter `daten/`; öffentliches Tool und private Daten bleiben unabhängige Repositories.

Benötigt werden Git-Zugriff zum Klonen/Pushen und authentifizierter API-Zugriff zum Prüfen der Privatheit. Vorhandene HTTPS-Git-Credentials können für beide verwendet werden. Die Einrichtung startet keinen eigenen Login; eine GitHub-Anmeldung im Git Credential Manager vorher einrichten.

Alternativ einen GitHub-Token mit lesendem Zugriff auf die Metadaten des Datenrepos über `GH_TOKEN` oder `GITHUB_TOKEN` in der aktuellen Prozessumgebung bereitstellen. Vor der ersten Einrichtung reicht `daten/.env` dafür nicht, weil der Ordner erst angelegt wird. Danach kann der Token auch lokal dort stehen. Die Git-Anmeldung zum Push bleibt zusätzlich erforderlich; ein SSH-Schlüssel allein erlaubt keine API-Privatheitsprüfung. [GitHub: Metadatenzugriff](https://docs.github.com/en/rest/repos/repos#get-a-repository).

Fehlende Bestätigung, API-Ausfall oder öffentliches Ziel sperren Einrichtung und Datenveröffentlichung. Passwörter und Tokens niemals ausgeben oder committen.

## Git-Autor

Falls noch kein Git-Autor eingerichtet ist, nach `setup_workspace.py` ausschließlich im privaten Datenrepo setzen:

```powershell
git -C daten config user.name 'DEIN NAME'
git -C daten config user.email 'DEINE E-MAIL'
```

Danach initialen Datencommit und `archiv init` wie in der README ausführen. Normale Toolcommits sind durch lokale Hooks gesperrt; eigene vorhandene Hooks werden nicht überschrieben.

## Archivpasswort und Wiederherstellung

`buchhaltung passwort einrichten` richtet ein neues Passwort mit mindestens 16 Zeichen ein. Verwende ein zufälliges Passwort oder eine Passphrase mit mehreren Wörtern. Das Archivpasswort ist unabhängig von GitHub-, GMX- und eBay-Zugangsdaten. Es steht lokal im Klartext in `daten/.env` unter `ENCRYPTION_PASSWORD`; diese Datei wird nicht eingecheckt. Den Rechnerzugang deshalb ebenfalls schützen.

Das Tool erzeugt einen zufälligen langen Datenschlüssel. Nur dessen passwortverschlüsselte Hülle wird in `daten/buchhaltung/key.json` versioniert und gesichert. Backup und Schlüsselhülle allein reichen nicht: Ohne das passende Passwort ist keine Wiederherstellung vorgesehen, und weder GitHub noch Bitcoin können die Daten entschlüsseln. Passwortmanager plus unabhängig verwahrte Notfallkopie verwenden. Das Passwort niemals in die Verfahrensdokumentation schreiben.

Nach `archiv init` mit `buchhaltung passwort pruefen` das Passwort verdeckt aus Erinnerung oder der getrennten Sicherung eingeben. Dieser Befehl prüft es am echten Datenschlüssel und speichert die Eingabe nicht. Er ersetzt keinen vollständigen Restoretest.

Das Dashboard erinnert freiwillig an die Eingabe. Diese Erinnerung ist überspringbar und prüft das Passwort bewusst nicht. Es enthält weder Passwort noch zusätzlichen Passwort-Prüfwert. Nur der Erinnerungszeitpunkt wird, soweit der Browser es erlaubt, für 24 Stunden lokal gespeichert. Die Eingabe wird verworfen; es entsteht kein Passwortschutz für das HTML.

**Passwort nicht durch Bearbeiten der `.env` ändern.** Ein Passwortwechsel benötigt ein geprüftes Neuverschlüsseln der Schlüsselhülle; dafür gibt es derzeit keinen Helfer. Bestehende Sicherungen und historische Schlüsselhüllen benötigen weiterhin das dazu passende Passwort.

Auf einem Ersatzrechner für `sicherung wiederherstellen PAKET --password-file PFAD_ENV --output NEUES_ZIEL` eine lokale Datei `PFAD_ENV` mit genau `ENCRYPTION_PASSWORD='DAS-GESICHERTE-PASSWORT'` anlegen. Diese Datei gehört weder ins Backup noch in Git. Das Paket enthält die Schlüsselhülle, beide Git-Historien und Wiederherstellungshinweise. Eine Wiederherstellungsprobe mit der getrennten Passwortkopie durchführen.

## eBay und GMX/DHL

Alle Werte gehören in `daten/.env`. Platzhalter ersetzen; vorhandene Werte erhalten:

```dotenv
ENCRYPTION_PASSWORD='DEIN-STARKES-PASSWORT'
EBAY_APP_ID='DEINE-APP-ID'
EBAY_DEV_ID='DEINE-DEV-ID'
EBAY_CERT_ID='DEINE-CERT-ID'
EBAY_AUTHNAUTH_TOKEN='DEIN-PRODUCTION-USER-TOKEN'
GMX_EMAIL='DEINE-GMX-ADRESSE'
GMX_PASSWORD='DEIN-GMX-ODER-APP-PASSWORT'
```

### eBay

1. Im eBay Developers Program ein Entwicklerkonto und Production-Anwendungsschlüssel einrichten. App-ID, Dev-ID und Cert-ID aus diesem Schlüsselsatz übernehmen.
2. Unter **User Tokens** einen **Production Auth’n’Auth-Token** für das eigene Verkäuferkonto erzeugen. Als `EBAY_AUTHNAUTH_TOKEN` hinterlegen; dieser Trading-API-Client verwendet keinen OAuth-App-Token. Abgelaufene oder widerrufene Tokens ersetzen. [eBay: Token-Anleitung](https://developer.ebay.com/devzone/xml/docs/howto/tokens/gettingtokens.html).
3. Verbindung mit `.venv/Scripts/buchhaltung.exe ebay --days 30 --limit 10 --paid-only` prüfen.

Deutschland (`EBAY_SITE_ID=77`) und Production (`EBAY_SANDBOX=false`) sind voreingestellt. Der Abruf erstellt keine Rechnung. `buchhaltung abgleich ebay --days 90 --save` speichert einen Kontrollabgleich verschlüsselt. Für tägliche Ausführung einen Scheduler einrichten; kein Gebührenimport oder Bankabgleich.

### GMX und DHL

1. In den GMX-Einstellungen den POP3-/IMAP-Zugriff einschalten. [GMX: Zugang und Serverdaten](https://hilfe.gmx.net/pop-imap/imap/imap-serverdaten.html).
2. GMX-Adresse und Passwort eintragen. Bei Zwei-Faktor-Authentifizierung ein [GMX-App-Passwort](https://hilfe.gmx.net/sicherheit/2fa/anwendungsspezifisches-passwort.html) verwenden. Voreingestellt: `imap.gmx.net`, TLS-Port `993`. Bei Bedarf `GMX_IMAP_HOST`/`GMX_IMAP_PORT` ergänzen.
3. DHL-Bestätigungsmails im Posteingang dieses Postfachs aufbewahren. Der Helfer durchsucht `INBOX` nach Sendungsnummer oder Text und lädt unterstützte Rechnungslinks herunter:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/find_dhl_receipt.py 'SENDUNGSNUMMER' --download --output-dir C:/bk/belegpruefung/dhl
```

Falls die Sendungsnummer nichts findet, mit `Maxibrief` oder `Online Frankierung` suchen. Datum, Produkt und Betrag mit dem Verkauf abgleichen; ein Treffer allein beweist keine Zuordnung. Fehlt ein unterstützter Rechnungslink oder blockiert DHL den Download, Originalbeleg separat einreichen. Die PDF entsteht hier außerhalb beider Repos. Mit `buchhaltung beleg inspect PFAD` prüfen und erst nach konkreter Freigabe buchen. Weitere Belege ebenso aus Downloads einlesen.

## Vine

Vine ist optional. Ohne `VINE_BACKEND_URL` und `VINE_BACKEND_TOKEN` wird die Bestandsprüfung ausdrücklich als nicht konfiguriert protokolliert, ohne den eBay-Entwurf zu blockieren. Sind beide gesetzt, wird das vorhandene kompatible Backend gelesen; Fehler werden nicht still übergangen. Unvollständige Konfiguration wird gemeldet. Es gibt keinen voreingestellten öffentlichen Backend-Zugang. Manuelle Rechnungen benötigen grundsätzlich keine dieser Anbindungen.

## Rechnungsprofil

Nach Archivinitialisierung mit `buchhaltung rechnung configure --interactive --last-number 0000` das Absenderprofil im Dialog erfassen und prüfen. `0000` gilt ausschließlich für einen leeren neuen Rechnungsbestand. Alternativ bleibt die folgende Profildatei für Automatisierungen unterstützt: JSON **außerhalb** von Tool- und Datenrepo erstellen, etwa `C:/bk/rechnungsprofil.json`:

```json
{
  "name": "DEIN NAME ODER FIRMENNAME",
  "street": "DEINE STRASSE UND HAUSNUMMER",
  "postal_code": "DEINE POSTLEITZAHL",
  "city": "DEIN ORT",
  "country_iso": "DE",
  "tax_number": "DEINE STEUERNUMMER",
  "small_business": true,
  "tax_note": "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
  "introduction": "Vielen Dank für Ihren Einkauf."
}
```

Dieser Einrichtungsweg gilt für deutsche Kleinunternehmer. Angaben prüfen und verschlüsselt übernehmen:

```powershell
.venv/Scripts/buchhaltung.exe rechnung configure --profile C:/bk/rechnungsprofil.json --last-number 0000
```

`0000` gilt nur für einen neuen leeren Rechnungsbestand. Vorhandene Rechnungen zuerst vollständig übernehmen und tatsächlichen Nummernstand prüfen. Ein bestehendes Profil nicht erneut initialisieren. Entwürfe starten im Probebetrieb ohne endgültige Nummer. [Nummernübergabe](handbuch.md#lokales-rechnungsprofil-und-nummernübergabe) und konkreter Rechnungsabschluss verlangen getrennte Freigaben.

## Bestehende Installation und Updates

Vorhandenes Archiv nicht neu initialisieren, keinen Datenschlüssel ersetzen. Passwort und private Repo-Konfiguration erhalten. Zuerst `buchhaltung pruefen` und `buchhaltung veroeffentlichen status` lesen. Offene Veröffentlichungen mit bisheriger Toolversion fortsetzen, bevor du aktualisierst.

```powershell
git pull --ff-only
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -X utf8 scripts/setup_workspace.py --hooks-only
```

Das private `daten/dashboard.html` zeigt kopierbare Befehle für den Toolordner. Monatsbackup und tatsächliches Schreiben/Rücklesen des Mediums nach dem [Handbuch](handbuch.md#verkaufsabgleich-lieferanten-erstattungen-und-sicherungsregister) durchführen; [betriebliche Verfahrensbeschreibung](betriebliche-ergaenzung-vorlage.md) privat vervollständigen.
