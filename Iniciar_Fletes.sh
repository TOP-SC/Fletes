#!/usr/bin/env bash
# Control de Fletes — arranque en servidor Linux (equivalente a Iniciar_Fletes.bat).
# Uso: ./Iniciar_Fletes.sh
# Deja API + Streamlit en segundo plano (sobrevive al cerrar SSH).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3 || command -v python)"
fi

API_HOST="127.0.0.1"
API_PORT=8000
UI_PORT=8501
export PYTHONPATH="$ROOT/backend"
export FLETES_API_URL="http://127.0.0.1:${API_PORT}/api/v1"

mkdir -p "$ROOT/logs" "$ROOT/run"

_free_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  elif command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti:"${port}" 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

_stop_pidfile() {
  local pf="$1"
  if [[ -f "$pf" ]]; then
    local pid
    pid="$(cat "$pf")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pf"
  fi
}

echo "========================================"
echo "  Control de Fletes — Iniciando..."
echo "========================================"
echo

echo "[1/4] Deteniendo instancias anteriores..."
_stop_pidfile "$ROOT/run/api.pid"
_stop_pidfile "$ROOT/run/ui.pid"
_free_port "$API_PORT"
_free_port "$UI_PORT"
sleep 1

echo "[2/4] Iniciando API (puerto ${API_PORT})..."
cd "$ROOT/backend"
nohup "$PY" -m uvicorn app.main:app --host "$API_HOST" --port "$API_PORT" \
  >>"$ROOT/logs/api.log" 2>&1 &
echo $! >"$ROOT/run/api.pid"

echo "[3/4] Esperando API..."
cd "$ROOT"
if ! "$PY" "$ROOT/scripts/wait_api.py"; then
  echo "ERROR: la API no respondió. Ver logs/api.log"
  exit 1
fi

echo "[4/4] Iniciando interfaz web (puerto ${UI_PORT})..."
cd "$ROOT"
nohup "$PY" -m streamlit run frontend/streamlit_app.py \
  --server.address 0.0.0.0 \
  --server.port "$UI_PORT" \
  --server.headless true \
  >>"$ROOT/logs/ui.log" 2>&1 &
echo $! >"$ROOT/run/ui.pid"

SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[[ -z "$SERVER_IP" ]] && SERVER_IP="127.0.0.1"
LINK_CLIENTE="http://${SERVER_IP}:${UI_PORT}"
echo "$LINK_CLIENTE" >"$ROOT/LINK_CLIENTE.txt"

echo
echo "Listo — aplicación en segundo plano."
echo
echo "  >>> LINK PARA EL CLIENTE (único acceso):"
echo "  >>> ${LINK_CLIENTE}"
echo
echo "  (La API corre solo en el servidor, no hace falta otro link.)"
echo
echo "  Logs:      ${ROOT}/logs/"
echo "  Detener:   ${ROOT}/Detener_Fletes.sh"
echo "  Estado:    ${ROOT}/Estado_Fletes.sh"
echo
echo "IMPORTANTE: esto NO arranca solo al reiniciar la VM."
echo "Para arranque automático al encender el servidor:"
echo "  sudo ${ROOT}/deploy/instalar_servicio.sh"
echo
