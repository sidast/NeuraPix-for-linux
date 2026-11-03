# NeuraPix 1.0.0

**Gar nicht mal so unintelligente Bildverwaltung**

NeuraPix ist eine lokale Linux-Anwendung zur Bildverwaltung, Gesichtserkennung und Zuordnung von Gesichtern zu Personen.

## Supported platform

- Linux x86_64
- Linux Mint 22.x
- Ubuntu 24.04 or newer
- Debian 13 (subject to package availability)
- Python 3.10 or newer; Python 3.12 is recommended

## Install

The installer creates an isolated virtual environment under `~/.local/opt/neurapix`, installs the Python dependencies, installs the application icon, and asks separately whether to create a menu entry and a desktop shortcut.

Run `./install.sh` from the extracted project directory.

System prerequisites that cannot reliably be installed without administrator privileges:
- Python 3 with Tkinter support (`python3-tk`)
- Python venv support (`python3-venv`)
- GTK 3 introspection bindings for the optional system tray (`gir1.2-gtk-3.0`, `python3-gi`)

If these are missing, install them through the distribution's package manager. The installer itself does not request root access.

## Start

After installation, run `neurapix` or launch it from the application menu.

## Data and configuration

- Application: `~/.local/opt/neurapix/`
- User data: `~/.local/share/neurapix/`
- Configuration: `~/.config/neurapix/`

The first start copies legacy databases and thumbnails when found. Original files are retained. Backups should be made before migration and before updates.

## Uninstall

Run `./uninstall.sh` from the extracted installation bundle. Personal data is retained unless the user explicitly confirms its deletion.

## Security

Dependencies are installed from the configured Python package index over HTTPS. The installer does not run as root. Package hashes are not pinned in this initial release; reproducible hash-locked installation remains a release-hardening task.

## Development

Create a virtual environment, install `requirements.txt`, then run `python gui.py`. The desktop launcher uses `start_neurapix.py` to display the splash screen while the GUI initializes.
