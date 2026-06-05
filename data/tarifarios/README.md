# Tarifarios — carpeta de carga

Colocá acá los Excel del tarifario trimestral (Clickpac, Limansky, etc.).

## Dónde copiar los archivos

```
Fletes/data/tarifarios/
├── README.md          (este archivo)
├── clickpac_Q1_2026.xlsx
├── limansky_Q1_2026.xlsx
└── ...
```

No hace falta renombrarlos de forma especial; la app lee todos los `.xlsx` de esta carpeta.

## Cómo cargarlos en la app (versiones por proveedor)

1. Copiá los archivos en esta carpeta.
2. Abrí la app → **Configuración** → pestaña **Tarifarios**.
3. Clic en **Escanear carpeta** — se crean **borradores** por hoja (CLICPAQ, FRANSOF, etc.).
4. Revisá el **preview/diff** y **Activá** solo los proveedores que cambiaron.
5. Si un proveedor no tenía versión activa, la primera se activa automáticamente.
6. Si los **precios son idénticos** a la versión activa, ese proveedor se **omite** (no crea borrador ni renueva).

Después: **Recalcular costos con tarifario** y en **Envíos interior** → **Procesar todo**.

Cadencia sugerida por proveedor: `data/tarifarios_cadencia.json`.
Rollback disponible si activaste una versión por error.

## Tarifario histórico por fecha

Al consultar el **Maestro** o **Fletes** de un mes anterior, el cobro se calcula con el
tarifario **vigente en la fecha de entrega** (o pedido si no hay entrega) de cada remito —
no con el tarifario actual. Las versiones históricas quedan guardadas al activar una nueva.

## Archivo unificado Mantello

Si el Excel tiene hojas **clicpaq**, **fransof**, **alfaro**, **LBO CP** y **fletes sucursales**
(como `TARIFARIOS INTERIOR y FLETES SUC 2026.xlsx`), la app lo detecta sola y convierte
cada hoja a filas de tarifa:

| Hoja | Proveedor | Uso |
|------|-----------|-----|
| clicpaq | CLICKPAC | Interior — matriz provincia × tipo producto × CEDOL |
| fransof | FRANOV | Santa Fe — tarifa por localidad (catálogo `fransof_localidades.json`) |
| alfaro | ALFARO | NOA — Jujuy / Salta / Tucumán |
| LBO CP | LBO | Córdoba — servicios por km |
| fletes sucursales | FLETES_SUC | CABA/GBA — ver `docs/TARIFA_LOGISTICA_CABA_GBA.md` |

No hace falta reformatear el Excel: copialo tal cual en esta carpeta.

## Formato tabla simple (alternativo)

Una fila por tarifa. Columnas (nombres flexibles en español):

| Columna | Obligatorio | Ejemplo |
|---------|-------------|---------|
| proveedor | Sí | CLICKPAC |
| provincia | Sí | Santa Fe |
| localidad | Sí | Rosario |
| tipo_producto | Recomendado | COLCHON, SOMIER, BASE |
| medida | Recomendado | 100x200, 160x200 |
| precio | Sí | 240000 o 240.000 |
| cedol | Opcional | índice trimestral |
| vigencia_desde / vigencia_hasta | Opcional | 2026-01-01 |
| notas | Opcional | |

También acepta alias: `tarifa`, `importe`, `valor` en lugar de `precio`.

## Importes con muchos ceros

La app normaliza automáticamente:

- `240000.000000000` → **240000** ($240.000)
- `240.000` (formato miles AR) → **240000**
- `12500,50` → **12500.5**

Si un precio se ve mal después de importar, revisá que la celda en Excel no tenga formato raro; podés dejar el número como entero (240000).

## Plantilla de ejemplo

En `data/plantilla_tarifario.xlsx` hay un ejemplo mínimo para copiar estructura.
