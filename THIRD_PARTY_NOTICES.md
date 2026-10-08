# Lizenzen der Abhängigkeiten

Der eigene Quellcode steht unter MIT (`LICENSE`). Diese Angabe lizenziert keine
Fremdbibliotheken um und ist keine Zusage, dass die vollständige Anwendung mit
allen Abhängigkeiten ausschließlich unter MIT weitergegeben werden kann.

## PyMuPDF / MuPDF

PyMuPDF wird für PDF-Text, Vorschaubilder und eingebettete XML verwendet und ist
unter GNU AGPLv3 oder einer separaten kommerziellen Artifex-Lizenz erhältlich.
Dieses Projekt verwendet die freie AGPL-Ausgabe. Die unveränderten Original-PDFs
bleiben erhalten; PyMuPDF erstellt hier keine eigenen Rechnungs-PDFs.

- [Hersteller: Lizenzwege und Pflichten](https://pymupdf.io/licensing)
- [PyMuPDF-Quellcode und AGPL-Lizenz](https://github.com/pymupdf/PyMuPDF)
- [MuPDF-Quellcode](https://github.com/ArtifexSoftware/mupdf)

Kostenlose oder nicht gewerbliche Nutzung hebt die Lizenzpflichten nicht auf.
Der Toolquellcode ist öffentlich verfügbar und MIT erlaubt eine AGPL-kompatible
Weitergabe. Bei Weitergabe einer kombinierten Anwendung sind die AGPL-Pflichten
zu beachten; eine solche Kombination darf nicht als ausschließlich MIT angeboten
werden. Lizenz-/Urheberhinweise und der erforderliche korrespondierende Quellcode
der tatsächlich ausgelieferten Versionen müssen verfügbar bleiben. Ein verändertes
Netzwerkangebot erfordert zusätzlich die jeweils einschlägige Quellcodebereitstellung.

Der Release enthält Toolquellcode zum Klonen, keine gebündelten Interpreter oder
PyMuPDF-/MuPDF-Binaries. Die Bibliotheken werden aus ihren offiziellen Python-Paketen
installiert. Wer selbst Binaries oder vollständige Installationspakete verteilt,
muss die entsprechenden Lizenz- und Quellcodepflichten eigenständig erfüllen.
Buchhaltungsbelege und Nutzerdaten werden dadurch nicht zu öffentlich zu verteilendem
Softwarequellcode.

## EN16931-Validierung

Die enthaltenen unveränderten CEN-Validierungsartefakte stehen unter EUPL 1.2.
Lizenztext, Herkunft und Prüfsummen: `src/autobookkeeping/validation/`.

## Weitere Python-Abhängigkeiten

Die jeweiligen Lizenztexte in den installierten Paketen gelten unverändert.
`pyproject.toml` bezeichnet die direkten Abhängigkeiten. Das Release-Testprotokoll
nennt die tatsächlich geprüften Paketversionen. Dies ist kein Offline-Paketspiegel
und keine pauschale Lizenzierung aller Abhängigkeiten unter MIT.
