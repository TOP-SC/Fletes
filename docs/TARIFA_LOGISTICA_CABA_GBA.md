# Tarifario logística CABA / GBA (SommierCenter)

Referencia operativa **LOGÍSTICA** (actualización 06/02/2026).  
Fuente: planilla *Expreso CABA y GBA* — cargada en Excel **fletes sucursales** del tarifario Mantello.

## Costo proveedor vs cobro al cliente

En la app (`costo_conceptos.py`, `cobro_logistica_service.py`):

- **Costo proveedor**: lo que nos cobra FLETES_SUC / red según tarifario. Va en `costo_tarifario` y columnas LOGISTICA + SEGURO del maestro.
- **Cobro al cliente**: en CABA/GBA suele ser **$0** (flete bonificado). La columna **total** del maestro refleja eso; no anula el costo proveedor.

## Zonas (km desde sucursal de origen)

| Zona | Hasta |
|------|--------|
| 1 | 10 km |
| 2 | 20 km |
| 3 | 40 km |
| 4 | Más de 40 km |

**Wamaro:** $3.500 × km (todas las categorías).  
**Cliente:** tabla fija por zona y categoría (abajo).

## Categorías de cobro (un envío = un pedido)

No se cobra por renglón suelto. Se interpreta el **NRO PEDIDO** y se elige **una** fila:

| Categoría tarifario | Medidas ancho (cm) | m³ ref. |
|---------------------|-------------------|---------|
| Colchón 1 pl. | 80, 90, 100 | 0,5 |
| Colchón 2 pl. | 130, 140, 150 | 0,8 |
| Colchón Queen/King | 160, 180, 200 | 1,0 |
| Conjunto 1 pl. | 80-100 | 0,8 |
| Conjunto 2 pl. | 130-150 | 1,3 |
| Conjunto Queen/King | 160-200 | 1,8 |
| Divanes / sillones / muebles | — | 1,3 |

### Reglas de armado (pedido)

- Varios renglones con el **mismo NRO PEDIDO** = **un** flete.
- **Colchón + somier/base** (misma venta) → tarifa **CONJUNTO** (no colchón + somier por separado).
- **Solo colchón** → tarifa **COLCHON**.
- **Queen/King conjunto** → **2 somiers** (no uno).
- **Patas** (pack 6 por somier): accesorio, **sin flete extra**.
- **Diván** (colchón ~1×2 + base/diván): tarifa **MUEBLES** / divanes.

## Seguro

**$3.000** por envío/caso (valor fijo en la app).

## Adicionales (a implementar en fases)

- Hora de abastecimiento: $20.000
- Logística inversa: sin cargo si vuelve a la misma sucursal
- Escaleras: $9.000 por piso desde el **2.º** (PB y 1.º sin cargo)

## Interior (CLICPAQ / crossdock)

Misma lógica de **pedido único**: un cobro por tipo CONJUNTO/COLCHON/MUEBLES + banda; crossdock suma CLICPAQ + última milla **una vez por pedido**.
