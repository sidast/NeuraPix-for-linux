#!/usr/bin/env bash
set -euo pipefail
INSTALL="$HOME/.local/opt/neurapix"
read -r -p "NeuraPix und Startmenü-/Desktop-Einträge entfernen? [J/n] " ANSWER
ANSWER="${ANSWER:-J}"
[[ "$ANSWER" =~ ^[JjYy] ]] || exit 0
rm -rf "$INSTALL" "$HOME/.local/bin/neurapix" \
  "$HOME/.local/share/applications/neurapix.desktop" \
  "$HOME/.local/share/icons/hicolor/16x16/apps/neurapix.png" \
  "$HOME/.local/share/icons/hicolor/32x32/apps/neurapix.png" \
  "$HOME/.local/share/icons/hicolor/48x48/apps/neurapix.png" \
  "$HOME/.local/share/icons/hicolor/64x64/apps/neurapix.png" \
  "$HOME/.local/share/icons/hicolor/128x128/apps/neurapix.png" \
  "$HOME/.local/share/icons/hicolor/256x256/apps/neurapix.png" \
  "$HOME/.local/share/icons/hicolor/512x512/apps/neurapix.png"
DESK="$(xdg-user-dir DESKTOP 2>/dev/null || printf '%s/Desktop' "$HOME")"
rm -f "$DESK/neurapix.desktop"
read -r -p "Auch persönliche Daten und Einstellungen löschen? [j/N] " DATA
if [[ "$DATA" =~ ^[JjYy] ]]; then
  rm -rf "$HOME/.local/share/neurapix" "$HOME/.config/neurapix"
  echo "Persönliche Daten wurden gelöscht."
else
  echo "Persönliche Daten bleiben erhalten."
fi
echo "NeuraPix wurde deinstalliert."
