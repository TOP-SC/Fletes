# Cobertura FRANSOF por localidad

Archivo maestro: **`fransof_localidades.json`**

FRANSOF no cubre solo Rosario: opera en **varias localidades**, principalmente en **Santa Fe** (Rosario, Granadero Baigorria, San Lorenzo, Rafaela, Santa Fe capital, etc.) y algunas excepciones del tarifario (p. ej. San Francisco en Córdoba, Paraná en Entre Ríos).

## Origen

| Fuente | Uso |
|--------|-----|
| `localidades fransof.xlsx` | Zonas 1–7 (imagen / listado operativo) |
| Hoja **fransof** del tarifario Mantello | Localidades adicionales con tarifa |

Regenerar el JSON:

```bash
cd backend
python scripts/extraer_fransof_localidades.py
```

(O pasar ruta al tarifario: `python scripts/extraer_fransof_localidades.py "S:\...\TARIFARIOS....xlsx"`)

## En la app

- `es_zona_fransof(provincia, localidad)` — reemplaza el criterio «solo Rosario»
- Afecta: pestaña FRANSOF, crossdock última milla, sugerencia de proveedor
- Si el destino está en el catálogo y hay tarifa FRANSOF, entra en la vista y puede auto-asignarse

Códigos no listados siguen resolviéndose solo por tarifario importado.
