#!/usr/bin/env bash
# Instala API + Streamlit como servicios systemd (arranque automático al boot).
# Uso: sudo ./deploy/instalar_servicio.sh
set -euo pipefail

if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "Ejecutá con sudo: sudo $0"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLETES_USER="${SUDO_USER:-top}"
PY="$ROOT/.venv/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "No existe el venv en $ROOT/.venv"
  echo "Primero: cd $ROOT && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

mkdir -p "$ROOT/logs" "$ROOT/run"
chown -R "$FLETES_USER:$FLETES_USER" "$ROOT/logs" "$ROOT/run"

_render() {
  local src="$1"
  local dst="$2"
  sed \
    -e "s|@FLETES_ROOT@|${ROOT}|g" \
    -e "s|@FLETES_USER@|${FLETES_USER}|g" \
    "$src" >"$dst"
}

_render "$ROOT/deploy/fletes-api.service" /etc/systemd/system/fletes-api.service
_render "$ROOT/deploy/fletes-ui.service" /etc/systemd/system/fletes-ui.service

# Si corría con Iniciar_Fletes.sh, liberar puertos antes del servicio
if [[ -x "$ROOT/Detener_Fletes.sh" ]]; then
  sudo -u "$FLETES_USER" "$ROOT/Detener_Fletes.sh" || true
fi

systemctl daemon-reload
systemctl enable fletes-api.service fletes-ui.service
systemctl restart fletes-api.service
sleep 2
systemctl restart fletes-ui.service

SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[[ -z "$SERVER_IP" ]] && SERVER_IP="127.0.0.1"
LINK_CLIENTE="http://${SERVER_IP}:8501"
echo "$LINK_CLIENTE" >"$ROOT/LINK_CLIENTE.txt"
chown "$FLETES_USER:$FLETES_USER" "$ROOT/LINK_CLIENTE.txt"

echo
echo "=========================================="
echo "  Servicios instalados — arranque automático"
echo "=========================================="
echo
echo "  >>> LINK PARA EL CLIENTE (único acceso):"
echo "  >>> ${LINK_CLIENTE}"
echo
echo "  Al reiniciar la VM, la app vuelve sola (systemd)."
echo "  La API queda interna en el servidor (127.0.0.1:8000)."
echo "  Link guardado en: ${ROOT}/LINK_CLIENTE.txt"
echo
echo "Comandos útiles (solo administración):"
echo "  sudo systemctl status fletes-api fletes-ui"
echo "  sudo systemctl restart fletes-api fletes-ui"
echo "  tail -f ${ROOT}/logs/api.log ${ROOT}/logs/ui.log"
echo
echo "Recomendado en el router: IP fija DHCP para esta VM (${SERVER_IP})."
echo
