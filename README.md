# Control de Fletes

Automatización del control logístico SommierCenter / Wamaro.

## Stack

- **Backend**: FastAPI + SQLAlchemy + SQLite (`data/fletes.db`)
- **Frontend**: Streamlit

## Arranque rápido

**Doble clic** en `Iniciar_Fletes.bat` (instala dependencias la primera vez con `pip install -r requirements.txt`).

Abre el navegador en http://localhost:8501 y levanta API + interfaz automáticamente.

### Servidor Linux (VM / demo en red)

Equivalente al `.bat`, para dejar la app corriendo en segundo plano:

```bash
cd /opt/fletes          # carpeta del proyecto
chmod +x Iniciar_Fletes.sh Detener_Fletes.sh Estado_Fletes.sh deploy/instalar_servicio.sh
./Iniciar_Fletes.sh     # levanta API + Streamlit (sobrevive al cerrar SSH)
./Estado_Fletes.sh      # ver si está activo
./Detener_Fletes.sh     # detener
```

**Arranque automático** al encender el servidor (recomendado para producción/demo):

```bash
sudo ./deploy/instalar_servicio.sh
```

- El cliente **solo abre un link**: `http://<IP-del-servidor>:8501` (ej. `http://10.20.2.166:8501`).
- La API corre **por detrás** en el mismo servidor; no hace falta otro link ni puerto para el usuario.
- Tras un **apagado o reinicio** de la VM, la app **vuelve sola** si instalaste el servicio systemd.
- `Iniciar_Fletes.sh` solo (sin systemd) **no** sobrevive a un reinicio — sirve para pruebas.

Recomendado en red: reservar IP fija DHCP para la VM. El link queda en `LINK_CLIENTE.txt` en el servidor.

**Nombre en lugar de IP** (sin `:8501`):

```bash
# 1) En tu DNS interno: registro A  fletes.top  →  IP de la VM
# 2) En la VM:
sudo FLETES_HOST=fletes.top ./deploy/instalar_nginx.sh
```

El cliente queda con `http://fletes.top` (elegí el nombre que uses en tu DNS).

Logs en `logs/api.log` y `logs/ui.log`.

### Arranque manual (opcional)

```powershell
pip install -r requirements.txt
.\scripts\run_api.ps1    # terminal 1
.\scripts\run_ui.ps1     # terminal 2
```

## Mundo 1 — Flujo (orden)

| Paso | Fuente | Acción en la app |
|------|--------|------------------|
| 1 | Tango `Exportacion.xlsx` | Importar (acumula, no pisa). **Exportar siempre por fecha de entrega** (CD y Limansky) |
| 2 | Mail Clickpack (diario) | Import prefactura (`data/plantilla_clickpack.xlsx`) |
| 3 | — | Ejecutar **macheo** (remito normalizado, conjuntos colchón+somier) |
| — | Tarifario CEDOL | Import en **Tarifarios** → recalcular costos |
| 4 | Grilla postventa | Import + aplicar reglas (+25% gestión, $0 no paga, etc.) |
| 5 | Liquidación quincenal | Import + conciliar desvíos |

**Pipeline completo**: botón en UI que encadena reglas + macheo + postventa.

### Tarifarios

Copiá los Excel en **`data/tarifarios/`** (instrucciones en `data/tarifarios/README.md`).

En la app: **Configuración → Tarifarios → Importar todos los Excel de data/tarifarios**.

Los importes con ceros de más (`240000.000000000`) se normalizan a **240000** ($240.000).

### Plantillas (`data/`)

- `plantilla_tarifario.xlsx` — ejemplo de estructura
- `plantilla_clickpack.xlsx` — reporte proveedor
- `plantilla_postventa.xlsx` — grillas postventa
- `plantilla_liquidacion.xlsx` — liquidación 1–15 / 16–fin

### Reglas automáticas

- Excluye AMBA/GBA y retiro en sucursal (gris)
- Alerta Clickpack / crossdocking (amarillo)
- Entrega en cliente en interior sin Clickpack (naranja — error vendedor)
- Macheo: diferencia prefactura vs suma costos tarifarios (+ $30 seguro c/u)
- Postventa: gestión retiro +25%, rotura/expreso $0, etc.

## Mundos — avance (jun 2026)

| Mundo | Dev | Operación | Nota |
|-------|-----|-----------|------|
| **1 Interior** | 97% | 74% | Proveedor por transporte, alertas operativas. Falta prefactura + macheo |
| **2 Fletes AMBA/GBA** | Base entregada | Etapa 2 | Grilla, km, planilla Drive. Falta conciliación $ con prefactura del transportista local + datos Tango sucursal |
| **3 Duplicados interior** | 15% | 5% | No AMBA/Fletes. Pendiente spec |
| **Global** | **~78%** | **~58%** | Luces por columna, remitos R/RAR. Falta prefactura en rutina |

## Mundos siguientes

- **Mundo 2**: fletes CABA/GBA (FLETES_SUC, km) — sin cross-dock
- **Mundo 3**: duplicados / edge cases cross **solo interior**

## API

- Docs: http://127.0.0.1:8000/docs
- Prefijo: `/api/v1/mundo1/...`
