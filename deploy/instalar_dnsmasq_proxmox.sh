#!/usr/bin/env bash
# DNS local en nodo Proxmox: fletes.top → VM, resto → DC Azure.
# Ejecutar EN EL PROXMOX (root), no en la VM fletes.
#
# Uso:
#   sudo PVE_DNS_IP=10.20.2.91 FLETES_VM_IP=10.20.2.166 DC_DNS_IP=192.168.0.230 ./deploy/instalar_dnsmasq_proxmox.sh
set -euo pipefail

if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "Ejecutá en el nodo Proxmox como root: sudo $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PVE_DNS_IP="${PVE_DNS_IP:-10.20.2.91}"
FLETES_VM_IP="${FLETES_VM_IP:-10.20.2.166}"
DC_DNS_IP="${DC_DNS_IP:-192.168.0.230}"

if [[ ! -f /etc/debian_version ]] && [[ ! -f /etc/pve/.version ]]; then
  echo "AVISO: este script está pensado para Debian/Proxmox."
fi

echo "Instalando dnsmasq en Proxmox..."
echo "  Escucha DNS en:  ${PVE_DNS_IP}"
echo "  fletes.top  →    ${FLETES_VM_IP}"
echo "  Resto DNS   →    ${DC_DNS_IP}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq dnsmasq

if ss -ulnp 2>/dev/null | grep -q ':53 '; then
  echo
  echo "Puerto 53 UDP en uso:"
  ss -ulnp | grep ':53 ' || true
  echo "(Si es systemd-resolved en 127.0.0.53, no hay conflicto con ${PVE_DNS_IP}:53)"
fi

sed \
  -e "s|@PVE_DNS_IP@|${PVE_DNS_IP}|g" \
  -e "s|@FLETES_VM_IP@|${FLETES_VM_IP}|g" \
  -e "s|@DC_DNS_IP@|${DC_DNS_IP}|g" \
  "$SCRIPT_DIR/dnsmasq-fletes.conf" >/etc/dnsmasq.d/fletes-top.conf

# Desactivar dhcp en dnsmasq global si existiera
if grep -q '^dhcp-range=' /etc/dnsmasq.conf 2>/dev/null; then
  echo "AVISO: /etc/dnsmasq.conf tiene dhcp-range — revisá que no choque con tu red."
fi

systemctl enable dnsmasq
systemctl restart dnsmasq

echo
echo "=========================================="
echo "  dnsmasq activo en ${PVE_DNS_IP}"
echo "=========================================="
echo
echo "Prueba en el Proxmox:"
echo "  dig @${PVE_DNS_IP} fletes.top +short"
echo "  dig @${PVE_DNS_IP} google.com +short"
echo
echo "Las PCs que usen la app deben usar DNS: ${PVE_DNS_IP}"
echo "  (configuración de red → DNS manual, o DHCP del segmento 10.20.2.x)"
echo
echo "Link final (después de nginx en la VM): http://fletes.top"
echo
