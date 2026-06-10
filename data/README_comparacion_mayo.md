# Comparación maestro mayo 2026

## Origen de datos

| Fuente | Ubicación |
|--------|-----------|
| **Referencia (LOG diario)** | `S:\Administración\TOP\LOG -  Envios Fletes 200326\fletes envios log MAYO\...\5 MAY 2026\` — archivos `WAMARO TORTUGUITAS - DD_MM_2026.xlsx` y `WAMARO SA - ...` |
| **App** | Base `data/fletes.db` → maestro mayo 2026 (filtro **fecha de entrega**, estándar unificado) |

## Cómo reproducir

```bash
cd backend
python scripts/comparar_maestro_mayo.py
```

Genera: **`data/comparacion_mayo.xlsx`** (hojas: referencia, app_maestro, dif_logistica, dif_seguro, solo_referencia, solo_app).

## Seguro

- **App (desde jun/2026):** $3.000 por caso (`config.seguro_fijo`).
- **Excel LOG mayo:** columna **SEGURO = 30** en casi todos los casos.  
  Posible plantilla antigua o el 3000 está en **VALOR DECLARADO**, no en SEGURO. Revisar con administración.

## Clave de cruce

No coincide el número **ENVIO** Tango (103xxxxx) con el de muchos imports actuales.  
La comparación usa **remito normalizado** (`R-0178-…` → dígitos) cuando existe.

## Última corrida (resumen)

- Referencia: ~2.064 remitos únicos en mayo (2.115 filas).
- App: ~5.980 casos con remito en mayo.
- **En ambos:** 503 remitos.
- **Logística parecida** (±15% o ±$5.000): **263** de 503 (~52%).
- **Solo en LOG:** 1.561 (maestro manual sin importar o sin remito en Tango).
- **Solo en app:** 5.477 (más volumen Tango / rango abril+mayo / sin remito en LOG).

Las diferencias grandes de LOGISTICA suelen ser: tarifario distinto, pedido vs renglón, GBA mal clasificado como interior, o costo 0 en app.
