# Catálogo de sucursales

Archivo maestro: **`sucursales.json`** (mismo formato que Mantello).

- **codigo** (`id` en JSON): AV, BE, CA, CD, etc. — coincide con el tablero *Seguimientos centralizados*.
- **lat / lon**: puntos para distancias y auditoría de km (Mundo 2).
- Al iniciar la API se sincroniza automáticamente a la tabla `sucursales`.
- Resincronizar manual: **Configuración → Sistema → Resincronizar desde JSON** o `POST /api/v1/sucursales/sincronizar`.

Para actualizar direcciones, editá el JSON y resincronizá.
