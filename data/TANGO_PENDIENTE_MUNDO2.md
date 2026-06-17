# Qué bajar de Tango (cuando puedas) — Mundo 2 Fletes

La app **ya puede mostrar** fletes con el Tango que tengan cargado (envíos Amba/GBA en gris) y el tarifario **fletes sucursales**.  
Estos exports **mejoran** el módulo pero no bloquean la primera pantalla.

## Prioridad alta

1. **Seguimientos centralizados — Distribuidora (o el proveedor que usen para entregas locales)**  
   - Mismo rango de fechas que usan operativamente.  
   - Sucursales: las que correspondan (AV, BE, CA… o “Todas”).  
   - Export a Excel (mismo formato que `Exportacion.xlsx` si es posible).  
   - **Para:** ver todos los pedidos CABA/GBA con remito, domicilio, transporte.

2. **Columna o campo de sucursal de origen** (código AV, BE, CA…)  
   - Si el Excel trae sucursal en otra columna, mandá una fila de ejemplo.  
   - **Para:** ligar cada envío al catálogo `data/sucursales.json`.

## Prioridad media

3. **Km / distancia** (si existe reporte o columna en Tango).  
   - **Para:** asignar Zona1_10km … Zona4_40+km y auditar el flete local calculado vs lo facturado.

4. **Prefactura o liquidación del transportista de flete local (AMBA/GBA)** — cuando tengan formato estable.  
   - **Para:** cruce en pesos como Clickpack en interior (cualquier fletero local; el sistema no depende del nombre comercial).

## Ya en la app (no hace falta bajar de nuevo)

- Catálogo de **29 sucursales** con dirección y GPS (`data/sucursales.json`).  
- Tarifario **FLETES_SUC** desde Mantello (`fletes sucursales` en `data/tarifarios/`).

## Mientras tanto

En **Fletes** (menú) la grilla usa envíos ya importados marcados Amba/GBA.  
La columna **Sucursal** y **Zona km** quedarán completas cuando llegue el export con esos datos.
