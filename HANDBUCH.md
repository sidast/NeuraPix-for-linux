# NeuraPix 1.0.0 – Benutzerhandbuch

**Gar nicht mal so unintelligente Bildverwaltung**

## 1. Überblick

NeuraPix verwaltet Bildordner, erkennt menschliche Gesichter und unterstützt die Zuordnung erkannter Gesichter zu Personen. Die Bilddateien bleiben an ihrem ursprünglichen Speicherort.

## 2. Erster Start

1. NeuraPix starten.
2. Im Startbildschirm warten, bis die Anwendung geladen ist.
3. Einen oder mehrere Analyseordner hinzufügen.
4. Die gewünschten Bildformate in den Einstellungen aktivieren.

Beim ersten Start können die KI-Laufzeit und das Erkennungsmodell initialisiert werden. Dafür wird eine Internetverbindung benötigt, sofern die benötigten Komponenten noch nicht vorhanden sind.

## 3. Bildanalyse

Über **Bilder analysieren** startet die Analyse der ausgewählten Analyseordner. Fortschritt und Status werden im Hauptfenster angezeigt. Erkannte, noch nicht zugeordnete Gesichter erscheinen in der Warteschlange.

## 4. Personen verwalten

Unter **Bilder ansehen** können Personen ausgewählt und deren zugeordnete Bilder angezeigt werden. Über das Kontextmenü eines Bildes lässt sich eine Zuordnung ändern. Mehrere Personendatensätze können zusammengeführt werden.

## 5. Warteschlange

Die Warteschlange enthält Gesichter, die keiner bekannten Person sicher zugeordnet werden konnten. Nach einer manuellen Zuordnung kann die Datenbank für weitere Zuordnungen genutzt werden.

## 6. Duplikate und Datenbank

Im Menü **Datenbank** stehen Funktionen für Datenbankprüfung, Duplikatsuche, Export, Wiederherstellung und Backups zur Verfügung. Vor Wiederherstellungen wird eine zusätzliche Sicherung angelegt.

## 7. Einstellungen

Die Einstellungen umfassen unter anderem Analyseordner, Bildformate, Karussell, Statusanzeige, Mouseover-Vorschau und Verhalten beim Schließen.

## 8. Speicherorte

- Programm: `~/.local/opt/neurapix/`
- Persönliche Daten: `~/.local/share/neurapix/`
- Konfiguration: `~/.config/neurapix/`

Die persönlichen Daten sind unabhängig vom Installationsordner und bleiben bei einer normalen Deinstallation erhalten.

## 9. Backup und Wiederherstellung

Über **Datenbank → Backup jetzt erstellen** kann eine Sicherung erstellt werden. Backups liegen im Unterordner `backups` des Datenverzeichnisses. Vor größeren Änderungen sollte ein aktuelles Backup erstellt werden.

## 10. Fehlerbehebung

- **Programm startet nicht:** Python 3, Tkinter und venv-Unterstützung der Distribution prüfen.
- **System-Tray fehlt:** GTK-3- und GObject-Introspection-Pakete der Distribution prüfen.
- **Gesichtserkennung startet nicht:** Internetverbindung und Schreibrechte im Benutzerverzeichnis prüfen.
- **Bilder fehlen:** Prüfen, ob die ursprünglichen Bilddateien noch am gespeicherten Pfad liegen.
- **Datenmigration:** Die ursprünglichen Datenbankdateien werden beim Kopieren nicht gelöscht. Bei Problemen können sie erneut herangezogen werden.

## 11. Versionshistorie

### 1.0.0
Erste NeuraPix-Ausgabe mit neuem Branding, Linux-Installationsstruktur und Benutzerhandbuch.
