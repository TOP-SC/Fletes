# Fleteros locales (Fletes internos)

Entregas **sucursal → domicilio** donde el cliente ve **$0** pero la empresa paga a fleteros de confianza (BLAS, GAMA, ARMANDO RIOS, etc.).

## Origen de datos

Los vendedores cargan solicitudes en un Excel del Drive: **«Fletes solicitados sucursales»**.

En la red operativa suele estar en:

`S:\Administración\TOP\LOG -  Envios Fletes 200326\`

(ej. `Copia de Fletes Solicitados sucursales MAYO 2 - Logística.xlsx`).  
La carpeta mensual `4 ABR 2026` tiene LOG WAMARO / AMBA / CLP — **no** reemplaza este Excel.

**Mirada macro:** menú **Fletes** + **Configuración → Fleteros locales**.  
**Mirada micro (Modo TOP):** no aplica — es LOG interior canal 51/83, sin fleteros locales.

Columnas clave:

| Columna | Uso |
|---------|-----|
| `idFlete` | ID único del Drive (no duplicar al reimportar) |
| `Fletero` | Nombre del fletero local |
| `Articulos` | Texto con `Nro Pedido: 08053…` para machear con Tango |
| `LocalEntrega` | Sucursal que entrega |
| `FechaEntrega` / `FechaSolicitado` | Período de control |
| `EstadoFlete` | Se ignoran filas **Anulado** |

Plantilla de referencia: export Drive del mes en curso en carpeta LOG **S:**.

## Flujo en la app

1. **Configuración → Fleteros locales** → Importar Excel (sin macheo automático).
2. **Machear con maestro Fletes** → cruza contra casos Amba/GBA ya importados de Tango.
3. En **Fletes** aparece columna **FLETERO** y filtro por código (BLAS, GAMA…).
4. Resumen por fletero (entregas y total a pagar) en la misma pestaña de Configuración.

## API

- `POST /api/v1/fletes/internos/import` — subir Excel
- `POST /api/v1/fletes/internos/matchear` — remachear sin reimportar
- `GET /api/v1/fletes/internos/resumen?mes=&anio=&fletero=`
- `GET /api/v1/fletes/internos/casos?mes=&anio=&fletero=`
- `GET /api/v1/fletes/fleteros`

## Requisitos para el macheo

- Tango importado con pedidos Mundo 2 (AMBA/GBA).
- El `Nro Pedido` del Excel debe coincidir con el de Tango (se normalizan ceros a la izquierda).

Si hay entregas sin match: revisar que el pedido exista en Tango o que no esté anulado en el Drive.
