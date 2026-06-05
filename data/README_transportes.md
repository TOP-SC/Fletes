# Catálogo de transportes Tango

Archivo maestro: **`transportes.json`** — solo los códigos marcados en uso habitual (Excel `Transportes.xlsx`, filas amarillas).

Origen Tango: `COD_GVA24` (export `Transportes.xlsx`). El resto de códigos del Excel **no están mapeados**; la app sigue con reglas por texto/tarifario.

## Campos

| Campo | Significado |
|-------|-------------|
| `tipo` | retiro, sucursal, domicilio, interior_clicpaq, crossdock, costa, correo, especial |
| `zona` | amba, interior, costa, amba_capital_interior, etc. |
| `proveedor` | Sugerencia fija (CLICPAQ, FLETES_SUC) o null → lo resuelve destino/tarifario |
| `excluir_planilla` | No entra al maestro interior |
| `sin_flete_domicilio` | Sin costo logístico domicilio (retiros 02, 03, 41) |
| `es_canal_clicpaq` | Canal red CLICPAQ / prefactura |
| `alerta_uso` | Uso operativo cuestionable (ej. 84) |

## Resumen operativo

| Cód | Uso |
|-----|-----|
| 02, 03, 41 | Retiro sin flete domicilio (41 = retira en el momento) |
| 10 | Envío/retiro en sucursal (excluir maestro; **sí** puede tener costo logístico) |
| 40, 42, 49, 50 | Entregas AMBA/Capital |
| 51 | Expreso CLICPAQ al interior |
| 82 | Crossdocking |
| 48 | Correo / ventas web (mercadería chica) |
| 83 | Expreso Costa Atlántica |
| 84 | Alerta medida especial (mal uso habitual) |

## Sincronización

Al iniciar la API se carga en tabla `transportes`. Manual: `POST /api/v1/transportes/sincronizar`.

Para agregar códigos: editar JSON y resincronizar. Códigos no listados (ej. 81 Zippin) quedan sin regla de catálogo.
