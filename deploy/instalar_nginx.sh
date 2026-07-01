#!/usr/bin/env bash
# Nombre DNS + nginx (puerto 80) para acceder sin IP ni :8501.
#
# Uso:
#   sudo FLETES_HOST=fletes.top ./deploy/instalar_nginx.sh
#
# Antes: crear registro DNS A  fletes.top  →  IP de la VM (ver instrucciones al final).
set -euo pipefail

if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "Ejecutá con sudo: sudo FLETES_HOST=fletes.top $0"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLETES_HOST="${FLETES_HOST:-fletes.top}"
FLETES_USER="${SUDO_USER:-top}"
SERVER_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[[ -z "$SERVER_IP" ]] && SERVER_IP="127.0.0.1"

echo "Instalando nginx — host: ${FLETES_HOST} (VM ${SERVER_IP})"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx

sed \
  -e "s|@FLETES_HOST@|${FLETES_HOST}|g" \
  "$ROOT/deploy/nginx-fletes.conf" >/etc/nginx/sites-available/fletes

ln -sf /etc/nginx/sites-available/fletes /etc/nginx/sites-enabled/fletes
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl enable nginx
systemctl restart nginx

# Streamlit solo en localhost (el cliente entra por nginx :80)
if [[ -f /etc/systemd/system/fletes-ui.service ]]; then
  sed -i 's|--server.address 0.0.0.0|--server.address 127.0.0.1|g' /etc/systemd/system/fletes-ui.service
  systemctl daemon-reload
  systemctl restart fletes-ui.service
fi

LINK_CLIENTE="http://${FLETES_HOST}"
echo "$FLETES_HOST" >"$ROOT/FLETES_HOST.txt"
echo "$LINK_CLIENTE" >"$ROOT/LINK_CLIENTE.txt"
chown "$FLETES_USER:$FLETES_USER" "$ROOT/FLETES_HOST.txt" "$ROOT/LINK_CLIENTE.txt"

echo
echo "=========================================="
echo "  Nginx listo"
echo "=========================================="
echo
echo "  >>> LINK PARA EL CLIENTE:"
echo "  >>> ${LINK_CLIENTE}"
echo
echo "  Guardado en: ${ROOT}/LINK_CLIENTE.txt"
echo
echo "--- DNS (hacelo en tu servidor DNS interno) ---"
echo
echo "  Tipo:  A"
echo "  Nombre: ${FLETES_HOST%%.*}   (zona: ${FLETES_HOST#*.} si usás subdominio)"
echo "  O nombre completo: ${FLETES_HOST}"
echo "  IP:    ${SERVER_IP}"
echo
echo "  Ejemplo Active Directory:"
echo "    DNS Manager → zona interna → New Host (A)"
echo "    Name: ${FLETES_HOST%%.*}  IP: ${SERVER_IP}"
echo
echo "  Prueba desde una PC de la red (después del DNS):"
echo "    ping ${FLETES_HOST}"
echo "    curl -I http://${FLETES_HOST}"
echo
echo "  Si el DNS aún no propagó, prueba local en la VM:"
echo "    curl -I -H 'Host: ${FLETES_HOST}' http://127.0.0.1"
echo
