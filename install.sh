#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
INSTALL="$HOME/.local/opt/neurapix"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"
DATA="$HOME/.local/share/neurapix"
CONFIG="$HOME/.config/neurapix"

echo "NeuraPix 1.0.0 – Installation"
command -v python3 >/dev/null || { echo "Python 3 fehlt."; exit 1; }
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' || {
  echo "Python 3.10 oder neuer wird benötigt."; exit 1;
}
command -v python3-venv >/dev/null 2>&1 || true
mkdir -p "$HOME/.local/opt" "$BIN" "$APPS" "$DATA" "$CONFIG"

read -r -p "NeuraPix im Startmenü eintragen? [J/n] " MENU
MENU="${MENU:-J}"
read -r -p "Desktop-Verknüpfung erstellen? [j/N] " DESKTOP
DESKTOP="${DESKTOP:-N}"

rm -rf "$INSTALL"
mkdir -p "$INSTALL"
cp -a "$ROOT/." "$INSTALL/"
python3 -m venv "$INSTALL/venv" || {
  echo "Erstellung der Python-Umgebung fehlgeschlagen."
  echo "Installiere gegebenenfalls das Paket python3-venv deiner Distribution."
  exit 1
}
"$INSTALL/venv/bin/python" -m pip install --upgrade pip
"$INSTALL/venv/bin/python" -m pip install -r "$INSTALL/requirements.txt"

cat > "$BIN/neurapix" <<EOF
#!/usr/bin/env bash
exec "$INSTALL/venv/bin/python" "$INSTALL/start_neurapix.py" "\$@"
EOF
chmod +x "$BIN/neurapix"

for size in 16 32 48 64 128 256 512; do
  mkdir -p "$ICONS/\${size}x\${size}/apps"
  cp "$INSTALL/branding/hicolor/\${size}x\${size}/apps/neurapix.png" "$ICONS/\${size}x\${size}/apps/neurapix.png"
done

create_desktop() {
  local target="$1"
  cat > "$target" <<EOF
[Desktop Entry]
Type=Application
Name=NeuraPix
GenericName=Gar nicht mal so unintelligente Bildverwaltung
Comment=Intelligente Bildverwaltung und Gesichtserkennung
Exec=$BIN/neurapix
Icon=neurapix
Terminal=false
Categories=Graphics;Photography;
StartupNotify=false
EOF
  chmod 644 "$target"
}
if [[ "$MENU" =~ ^[JjYy] ]]; then create_desktop "$APPS/neurapix.desktop"; fi
if [[ "$DESKTOP" =~ ^[JjYy] ]]; then
  DESK="$(xdg-user-dir DESKTOP 2>/dev/null || printf '%s/Desktop' "$HOME")"
  mkdir -p "$DESK"
  create_desktop "$DESK/neurapix.desktop"
  if command -v gio >/dev/null; then gio set "$DESK/neurapix.desktop" metadata::trusted true 2>/dev/null || true; fi
fi
if command -v update-desktop-database >/dev/null; then update-desktop-database "$APPS" >/dev/null 2>&1 || true; fi
if command -v gtk-update-icon-cache >/dev/null; then gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true; fi
echo
echo "Installation abgeschlossen. Start: neurapix"
echo "Persönliche Daten: $DATA"
