# NeuraPix – Branding-Paket

Dieses Paket enthält das freigegebene NeuraPix-Logo und vorbereitete Linux-App-Icons.

## Dateien

- `neurapix-logo-master.png` – unveränderte Mastergrafik (quadratisch)
- `icons/neurapix-*.png` – PNG-Icons in gängigen Größen
- `hicolor/` – Linux-Icon-Theme-Struktur
- `neurapix.desktop.template` – Vorlage für den Linux-Startmenüeintrag

## Integration unter Linux

Bei der Installation werden die passenden Dateien nach
`~/.local/share/icons/hicolor/<größe>x<größe>/apps/neurapix.png`
kopiert. Die Desktop-Datei wird nach `~/.local/share/applications/neurapix.desktop`
installiert. Der Installer muss dabei den tatsächlichen Startbefehl in `Exec=`
eintragen.

## Hinweis

Die Mastergrafik enthält den Schriftzug und den dunklen Hintergrund. Eine
separate transparente Wortmarke sowie ein reines Symbol ohne Schriftzug sind
in diesem Paket noch nicht enthalten. Die Bilddateien sind Rastergrafiken,
keine editierbaren Vektordateien.
