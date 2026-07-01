#!/usr/bin/env bash
# Detiene API + Streamlit iniciados con Iniciar_Fletes.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

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
  local name="$2"
  if [[ -f "$pf" ]]; then
    local pid
    pid="$(cat "$pf")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
      echo "  ${name} detenido (pid ${pid})"
    else
      echo "  ${name}: pid ${pid} ya no estaba activo"
    fi
    rm -f "$pf"
  else
    echo "  ${name}: sin pidfile"
  fi
}

echo "Deteniendo Control de Fletes..."
_stop_pidfile "$ROOT/run/api.pid" "API"
_stop_pidfile "$ROOT/run/ui.pid" "Streamlit"
_free_port 8000
_free_port 8501
echo "Listo."
