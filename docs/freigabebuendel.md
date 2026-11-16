# Einmalige Freigabe eines Verkaufsbündels

Die betreute Verkaufsvorbereitung sammelt vor der Buchung alle verfügbaren Informationen. Der Agent prüft Quellen, Dubletten, Positionen und Beträge, erstellt den Rechnungsentwurf als lokale PDF/XML und sammelt den passenden DHL-Kostenbeleg einschließlich geprüfter Zahlungsdaten sowie die eindeutige Vine-Zuordnung. Diese Dateien liegen geschützt außerhalb beider Repositories. Es gibt dabei keine Rechnungsnummernvergabe, Archivänderung, Ausgabenbuchung oder Vine-Änderung. Gesondert beauftragte technische eBay-Kontrollnachweise dürfen weiterhin verschlüsselt veröffentlicht werden.

## Lokal vorbereiten

```powershell
.venv\Scripts\python.exe -X utf8 scripts/local_invoice.py prepare ORDER_ID --local-only --output EXTERNER_NEUER_ORDNER --receipt DHL_PDF --receipt-metadata GEPRUEFTE_METADATEN_JSON
```

Für Abholverkäufe ist `manual-prepare --metadata JSON --local-only --output EXTERNER_NEUER_ORDNER` vorgesehen. Bei fehlendem DHL-Beleg kann die Rechnung bereits lokal vorbereitet werden; das gesamte Bündel bleibt dann ausdrücklich offen. Das ältere `prepare` ohne `--local-only` archiviert einen Entwurf und ist daher nicht der automatische Vorbereitungseinstieg dieses Ablaufs. Bereits archivierte Entwürfe und deren Historie bleiben erhalten.

Der lokale Ordner enthält `rechnung.pdf`, `rechnung.xml`, `xml-validierung.json`, Metadaten, erforderliche Originale und `vorbereitung.json`. Er ist keine ausgestellte Rechnung. Die Vorbereitung hält ihre eigene Revision, die Entwurfsrevision, Originalhashes und die unverbindliche nächste Nummer fest. Die PDF/XML sind vor Vorlage zu prüfen. Bei mehreren freigegebenen Rechnungen die tatsächlichen fortlaufenden Nummern beim Abschluss unter Sperre ermitteln und zurücklesen; die Fortschreibung dieser unverbindlichen Nummernvorschau benötigt keine zweite Freigabe bei unveränderten Rechnungsinhalten.

Für einen DHL-Beleg gehören Betrag, Belegdatum, Versandart, Warenkorb-/Bestellbezug, Originalsteuer und Prüfbasis in die Metadaten. Ist die vollständige Zahlung belegt, außerdem `pay_date`, `paid_amount` und `payment_evidence` vorbereiten und im Bündel nennen. Ein Belegdatum allein belegt keinen Zahlungstag. Unbekannte Zahlung, unklarer DHL-Beleg oder mehrdeutige ASIN sind vor der Freigabe zu klären. Bei Abholung ohne Versandkosten die Ausnahme ausdrücklich festhalten. Für ein Nicht-Vine-Produkt ist eine geklärte Ausnahme erforderlich.

## Ein „Freigabe“ schließt das ganze vorgelegte Bündel ab

Vorher konkret vorlegen: lokale PDF, Revisionsbindung, Nummernvorschau, Rechnungspositionen und Gesamtbetrag, DHL-Betrag und belegte Zahlungsdaten beziehungsweise dokumentierte Ausnahme, vollständige Vine-Titel/ASINs mit Verkaufspreis und Datum. Erst wenn keine ungeklärten Komponenten mehr bestehen, als **freigabebereit** bezeichnen. Eine konkrete Auswahl oder Korrektur mit anschließendem „Freigabe“ ist ebenfalls eine Freigabe des dadurch eindeutig bestimmten Bündels.

Diese eine Freigabe deckt alle vorgestellten Komponenten einschließlich belegter Zahlungszuordnungen. Es folgt keine zusätzliche Nachfrage für Rechnung, Ausgabe, Zahlung oder Vine einzeln. Technische `--approved`-Parameter setzen dieselbe Chatfreigabe um; sie verlangen keine neuen Nutzerbestätigungen.

1. Mit `local_invoice.py adopt --preparation VORBEREITUNG_JSON --revision VORBEREITUNGSREVISION --approved` die freigegebene lokale Vorbereitung unverändert übernehmen. Der Helfer prüft Dateien/Hashes, aktuelle Verkaufsdaten, Absenderprofil und Dubletten. Er verändert keine anderen Entwürfe. Bei bereits vorhandenem identischem Entwurf erfolgt keine erneute Übernahme; die Rückgabe zeigt den aktuellen Nummernstand.
2. Mit `local_invoice.py issue ID --revision ENTWURFSREVISION --number NUMMER --approved` ausstellen und finale Nummer/Originale zurücklesen.
3. Den zugeordneten DHL-Kandidaten mit `expense ... --approved` buchen und zurücklesen. Die im Bündel geprüften vollständigen Zahlungsdaten werden dabei mit übernommen und für die lokale EÜR berücksichtigt. Falls eine separate `cash-record`-Zuordnung erforderlich ist, gilt dieselbe Freigabe für die bereits konkret vorgelegten Zahlungsdaten; vorhandene Zahlungen zuerst auf Dubletten prüfen.
4. Alle ausgewählten Vine-Datensätze mit den freigegebenen Preisen, Verkaufsdaten und vorhandenen Käuferangaben aktualisieren und zurücklesen. Für anonyme Abholung keine Namen/Adressen erfinden.
5. Rechnung, Ausgabe, Zahlungsfluss, Vine-Verknüpfung, Workflow, Dashboard und privaten GitHub-/OTS-Abschluss prüfen. Erst dann den Gesamtabschluss melden.

Bei einer Unterbrechung Veröffentlichung mit `status`/`resume` fortsetzen und nur fehlende Komponenten nachholen. Dieselbe Freigabe bleibt für unveränderte Werte gültig. Nur neue oder abweichende fachliche Angaben benötigen Klärung; bereits erledigte Schritte werden nicht wiederholt. Ein unbekannter Zahlungstag darf auch nach Freigabe nicht erfunden werden. Eine explizit als unbezahlt freigegebene Komponente bleibt ohne Zahlungsfluss.
