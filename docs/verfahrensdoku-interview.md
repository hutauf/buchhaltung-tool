# Betriebsabläufe mit einem Agenten beschreiben

Im Dashboard unter **Verfahrensdoku** steht ein vollständig kopierbarer Interview-Prompt.
`buchhaltung verfahrensdoku fragen` gibt ihn zusammen mit den Fragekennungen aus.
Ein Agent mit lokalem Zugriff kann die bestehende Beschreibung mit
`buchhaltung verfahrensdoku anzeigen --output NEUER_ORDNER_AUSSERHALB` lesen.
Er fragt höchstens zwei Themen gleichzeitig ab, übernimmt nur bestätigte Tatsachen
und lässt Unbekanntes ausdrücklich offen. Passwörter und Zugangswerte werden niemals
abgefragt. Es geht um die Beschreibung des Betriebs, keine Betriebsprüfung.

Alternativ führt das Terminal durch dieselben Themen:

```powershell
buchhaltung verfahrensdoku vorbereiten --interactive --output NEUER_ORDNER_AUSSERHALB
```

Für Agenten oder ausnahmsweise einen normalen Chat ist die Zwischenform ein
JSON-Objekt mit den Kennungen aus `fragen`. Jeder Wert enthält ausschließlich
`status` (`documented`, `open` oder `not_applicable`) und `text`. Nichtanwendbarkeit
benötigt eine Begründung. Auch einzelne Antworten können gezielt ergänzt werden;
andere bereits gespeicherte Antworten bleiben erhalten.

```powershell
buchhaltung verfahrensdoku vorbereiten --answers ANTWORTEN_AUSSERHALB.json --effective-from JJJJ-MM-TT --output NEUER_ORDNER_AUSSERHALB
```

Der neue Ordner enthält `betriebsangaben.json` und eine lesbare
`verfahrensdokumentation.md`. Der Befehl gibt die zu bestätigende Revision aus.
Er hat bis hierhin keine Betriebsangaben im Archiv gespeichert. Nach Durchsicht
und konkreter Freigabe:

```powershell
buchhaltung verfahrensdoku speichern --answers ENTWURFSORDNER/betriebsangaben.json --revision BESTAETIGTE_REVISION --approved
```

Dieser Schreibbefehl erhält frühere Fassungen verschlüsselt im Katalog und nutzt
die Datencommit-/Push-/OTS-Pipeline. Er stellt keine Rechnung aus und bucht keine
Ausgabe. Bestehende private Markdown-Ergänzungen werden nicht überschrieben;
den Übergang und gegebenenfalls abweichende Angaben bewusst dokumentieren.
Das Dashboard zeigt nur den Bearbeitungsstand, keine privaten Antworten. Der
vollständige Export enthält aktuelle und frühere Antworten im Katalog sowie als
lesbare Markdown-Dateien unter `dokumentation/betriebsangaben.md` und
`dokumentation/betriebsangaben-historie/`.
Ein normales ChatGPT ohne Repositoryzugriff kann nur einen Entwurf liefern und
darf keine Speicherung behaupten. Persönliche Betriebsdetails nur bewusst teilen.

Beschriebene Verfahren sind keine automatisch durchgeführten Kontrollen. Ein
Gültigkeitsdatum dokumentiert den angegebenen Beginn; es beweist keinen früheren
Erfassungszeitpunkt. Nicht umgesetzte Sicherungen bleiben als solche beschrieben.
