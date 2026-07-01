#!/usr/bin/env bash
# Muestra si API y Streamlit están corriendo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

_check_pidfile() {
  local pf="$1"
  local name="$2"
  if [[ -f "$pf" ]]; then
    local pid
    pid="$(cat "$pf")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      echo "  ${name}: activo (pid ${pid})"
      return 0
    fi
    echo "  ${name}: pidfile obsoleto (${pid})"
    return 1
  fi
  echo "  ${name}: no iniciado con Iniciar_Fletes.sh"
  return 1
}

_check_port() {
  local port="$1"
  local name="$3"
  if command -v ss >/dev/null 2>&1; then
    if ss -tln | grep -q ":${port} "; then
      echo "  Puerto ${port} (${name}): escuchando"
    else
      echo "  Puerto ${port} (${name}): libre"
    fi
  fi
}

SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[[ -z "$SERVER_IP" ]] && SERVER_IP="127.0.0.1"

echo "Estado — Control de Fletes"
echo "  Carpeta: ${ROOT}"
_check_pidfile "$ROOT/run/api.pid" "API"
_check_pidfile "$ROOT/run/ui.pid" "Streamlit"
_check_port 8000 "API"
_check_port 8501 "Streamlit"
echo
echo "  Interfaz: http://${SERVER_IP}:8501"
echo "  API:      http://${SERVER_IP}:8000/docs"

if systemctl is-active fletes-api.service >/dev/null 2>&1; then
  echo
  echo "  systemd fletes-api:   $(systemctl is-active fletes-api.service)"
  echo "  systemd fletes-ui:    $(systemctl is-active fletes-ui.service 2>/dev/null || echo n/a)"
fi
