# Prefactura Clickpack de prueba

Archivo: **`prefactura_clickpack_prueba.xlsx`**

Prefactura **ficticia** generada contra los remitos Clickpack/crossdocking que ya están en la base con tarifa calculada y color amarillo.

## Cómo usarla

1. **Configuración → Clickpack** → subir `prefactura_clickpack_prueba.xlsx`
2. Al importar se ejecuta el **macheo automático** (o usar **Macheo Clickpack** en Envíos interior)
3. Los remitos incluidos deberían pasar a **verde** si el importe coincide con el costo de control

## Remitos incluidos

| Remito | Cliente | Importe prefactura | Notas |
|--------|---------|-------------------|--------|
| R0017800318022 | PABLO PIERINO LONGHI | 70.491,52 | Conjunto colchón + base (2 renglones Tango) |
| R0017800318023 | LUCILA BELEN RONCHINI | 105.707,28 | Conjunto 3 renglones |
| R0017800318024 | LEANDRO HUGO TIMPANARO | 70.491,52 | Conjunto colchón + base |

## Importante — caso Villa Giardino (amarillo $0)

Remitos como **X0008000000283** (Villa Giardino, transporte vacío, costo $0) **no** se arreglan con Clickpack.

Ahí falta **tarifa / datos Tango**, no prefactura. Hay que corregir transporte en Tango, tener tarifario cargado y **Reaplicar reglas**.

## Regenerar el archivo

Desde `backend/`:

```bash
python scripts/generar_prefactura_prueba.py
```
