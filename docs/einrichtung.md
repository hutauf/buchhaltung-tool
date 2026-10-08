# Einrichtung und Anbindungen

Die [README](../README.md) enthält die Installationsbefehle für einen neuen Windows-Workspace. Hier stehen Zugangsdaten, Rechnungsprofil und Hinweise für bestehende Installationen. Alle Buchhaltungsbefehle im äußeren Toolordner starten.

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

Der aktuelle eBay-Rechnungsentwurf prüft zusätzlich den Vine-Bestand. `buchhaltung rechnung prepare` benötigt deshalb **auch** `VINE_BACKEND_URL` und `VINE_BACKEND_TOKEN` für ein vorhandenes kompatibles Vine-Backend. Kein voreingestellter öffentlicher Zugang; eine beliebige Backend-Adresse genügt nicht. Ohne diesen Zugang funktionieren Archiv, Dashboard und eBay-Abruf, aber dieser Rechnungsentwurfsablauf bricht ab.

## Rechnungsprofil

Nach Archivinitialisierung das eigene Absenderprofil als JSON **außerhalb** von Tool- und Datenrepo erstellen, etwa `C:/bk/rechnungsprofil.json`:

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
