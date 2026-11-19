#!/usr/bin/env bash
# ARASAKA RIPPERDOC // desinstalador
set -uo pipefail
APP_ID=arasaka-ripperdoc
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/$APP_ID"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
rm -f "$HOME/.local/bin/$APP_ID" "$APPS/$APP_ID.desktop" \
      "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/$APP_ID.svg" \
      "${XDG_DATA_HOME:-$HOME/.local/share}/icons/Arasaka/scalable/apps/$APP_ID.svg"
rm -rf "$DATA/app" "$DATA/venv" "${XDG_CACHE_HOME:-$HOME/.cache}/$APP_ID"
update-desktop-database -q "$APPS" 2>/dev/null
echo "■ Arasaka Ripperdoc removido. O que você desligou na inicialização continua desligado."
