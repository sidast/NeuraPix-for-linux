NeuraPix – Änderungen 1 und 2

Enthaltene Ersatzdateien:
- einstellungen.py
- gui.py
- erkennung.py
- funktionen.py

1) Relativer Gesichtsgrößenfilter:
   In den Einstellungen kann ein Wert von 0 bis 100 Prozent angegeben werden.
   Verglichen wird die Breite jedes Gesichtsrahmens mit der Breite des größten
   Gesichtsrahmens im selben Bild. 0 bedeutet keine Filterung.

2) Doppelte Bildzuordnungen:
   - Gesichter werden pro Bild als abgeschlossen/offen nachverfolgt.
   - Skip-Gesichter bleiben offen, bis sie zugeordnet oder ignoriert wurden.
   - Bei automatischer oder manueller Auflösung der Warteschlange wird der
     Bildstatus aktualisiert.
   - Ein Bild wird erst als verarbeitet markiert, wenn alle erkannten Gesichter
     abgeschlossen sind und keine Warteschlangeneinträge für den Hash übrig sind.
   - Doppelte identische Vektoren werden beim Erweitern einer Person vermieden.

Vor dem Ersetzen bitte NeuraPix vollständig schließen und die vier bisherigen
Dateien sichern. Die übrigen Programmdateien bleiben unverändert.
