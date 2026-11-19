#!/usr/bin/env bash
# ============================================================
#   ARASAKA RIPPERDOC // instalador (Zorin OS / Ubuntu / Debian)
#   Manutencao do Linux: drivers, atualizacoes, limpeza e inicializacao
#
#   Uso:  ./install.sh [-y]        (NAO rode com sudo)
# ============================================================
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID=arasaka-ripperdoc
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/$APP_ID"
BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
YES=0
for a in "$@"; do
  case "$a" in
    -y|--yes) YES=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Opcao desconhecida: $a"; exit 1 ;;
  esac
done

R=$'\e[38;2;227;18;31m'; RH=$'\e[38;2;255;59;71m'; W=$'\e[38;2;236;236;240m'; G=$'\e[38;2;120;120;130m'; B=$'\e[1m'; N=$'\e[0m'
STEP=0
step() { STEP=$((STEP + 1)); printf '\n%s%s[%02d]%s %s%s%s\n' "$R" "$B" "$STEP" "$N" "$W$B" "$*" "$N"; }
ok()   { printf '     %s■%s %s\n' "$R" "$N" "$*"; }
info() { printf '     %s›%s %s\n' "$R" "$N" "$*"; }
warn() { printf '     %s!! %s%s\n' "$RH" "$*" "$N"; }
die()  { printf '\n%s!! %s%s\n' "$RH" "$*" "$N"; exit 1; }

printf '\n%s%s   A R A S A K A   R I P P E R D O C%s\n' "$R" "$B" "$N"
printf '   %sManutencao do Linux%s\n' "$G" "$N"

[ "$EUID" -eq 0 ] && die "Rode como seu usuario normal (sem sudo): ./install.sh"
[ -f "$DIR/arasaka_ripperdoc/app.py" ] || die "Arquivos do app nao encontrados em $DIR"
command -v python3 >/dev/null || die "python3 nao encontrado"

if [ "$YES" -eq 0 ]; then
  printf '\n   Vai instalar o app (Python + Qt) e ferramentas de diagnostico (pciutils, mokutil).\n   %sContinuar? [s/N] %s' "$W" "$N"
  read -r r
  case "$r" in s|S|y|Y|sim|SIM) ;; *) echo "Cancelado."; exit 0 ;; esac
fi

step "Pacotes do sistema"
PKGS=(pciutils mokutil python3-venv python3-pip libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-image0
      libxcb-render-util0 libxcb-xinerama0 libxcb-shape0 libegl1 libnotify-bin)
MISSING=()
for p in "${PKGS[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || MISSING+=("$p"); done
if [ ${#MISSING[@]} -gt 0 ]; then
  info "instalando: ${MISSING[*]}"
  sudo apt-get update -qq || warn "apt update falhou"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${MISSING[@]}" || warn "alguns pacotes falharam"
fi
command -v lspci >/dev/null && ok "lspci disponivel" || warn "lspci ausente: a deteccao das placas de video fica limitada"

step "Ambiente Python (PySide6 / Qt 6)"
mkdir -p "$DATA"
[ -x "$DATA/venv/bin/python" ] || python3 -m venv "$DATA/venv" || die "falha ao criar o venv (falta python3-venv?)"
"$DATA/venv/bin/python" -m pip install -q --upgrade pip >/dev/null 2>&1
info "baixando PySide6 (~120 MB na primeira vez)..."
"$DATA/venv/bin/python" -m pip install -q --upgrade "PySide6-Essentials>=6.5" || die "falha ao instalar PySide6"
ok "PySide6 $("$DATA/venv/bin/python" -c 'import PySide6; print(PySide6.__version__)')"

step "Arquivos do app"
rm -rf "$DATA/app"
mkdir -p "$DATA/app" "$BIN" "$APPS" "$ICONS"
cp -r "$DIR/arasaka_ripperdoc" "$DATA/app/"
find "$DATA/app" -name '__pycache__' -prune -exec rm -rf {} +
cat > "$BIN/$APP_ID" <<EOS
#!/bin/sh
# ARASAKA RIPPERDOC launcher
export PYTHONPATH="$DATA/app\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$DATA/venv/bin/python" -m arasaka_ripperdoc "\$@"
EOS
chmod +x "$BIN/$APP_ID"
cp "$DIR/arasaka_ripperdoc/assets/$APP_ID.svg" "$ICONS/$APP_ID.svg"
# o tema de icones Arasaka tem um icone "arasaka": uma camada na pasta pessoal evita que ele substitua este
for th in /usr/share/icons/Arasaka "$HOME/.icons/Arasaka"; do
  if [ -f "$th/index.theme" ]; then
    UT="${XDG_DATA_HOME:-$HOME/.local/share}/icons/Arasaka"
    mkdir -p "$UT/scalable/apps"
    [ -f "$UT/index.theme" ] || cp "$th/index.theme" "$UT/index.theme"
    cp "$DIR/arasaka_ripperdoc/assets/$APP_ID.svg" "$UT/scalable/apps/$APP_ID.svg"
    break
  fi
done
cat > "$APPS/$APP_ID.desktop" <<EOS
[Desktop Entry]
Type=Application
Name=Arasaka Ripperdoc
GenericName=Manutencao do sistema
Comment=Drivers, atualizacoes, limpeza e inicializacao do Linux
Exec="$BIN/$APP_ID"
Icon=$APP_ID
Terminal=false
Categories=System;Settings;
Keywords=driver;nvidia;atualizar;limpeza;kernel;inicializacao;arasaka;ripperdoc;
StartupWMClass=$APP_ID
EOS
update-desktop-database -q "$APPS" 2>/dev/null
gtk-update-icon-cache -q -t "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor" 2>/dev/null
ok "atalho no menu: Arasaka Ripperdoc"


printf '\n%s%s ■ INSTALACAO CONCLUIDA%s\n' "$R" "$B" "$N"
printf '   %sAbra "Arasaka Ripperdoc" no menu (ou rode: arasaka-ripperdoc).%s\n\n' "$W" "$N"
