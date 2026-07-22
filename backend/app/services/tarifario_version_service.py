"""Versiones de tarifario por proveedor: borrador → activa → histórica."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import DATA_DIR, TARIFARIOS_DIR
from app.models import Envio, Tarifa, TarifarioVersion
from app.proveedores import PROVEEDOR_LABELS, normalizar_proveedor
from app.services.money_utils import parse_money
from app.services.tarifario_mantello_parser import (
    is_tarifario_mantello,
    parse_tarifario_mantello,
    parse_tarifario_mantello_por_proveedor,
)

CADENCIA_PATH = DATA_DIR / "tarifarios_cadencia.json"
PROVEEDORES_VERSIONADOS = ("CLICPAQ", "FRANSOF", "ALFARO", "LBO", "FLETES_SUC")


def _norm(value: str | None) -> str:
    return (value or "").strip().upper()


def _tarifa_key(
    provincia: str,
    localidad: str,
    tipo_producto: str,
    medida: str,
) -> tuple[str, str, str, str]:
    return (
        _norm(provincia),
        _norm(localidad),
        _norm(tipo_producto),
        _norm(medida).replace(" ", ""),
    )


def _cargar_cadencia() -> dict[str, Any]:
    if not CADENCIA_PATH.exists():
        return {}
    try:
        return json.loads(CADENCIA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fecha_en_vigencia(
    vig_desde: str | None,
    vig_hasta: str | None,
    fecha: str | None,
) -> bool:
    if not fecha:
        return True
    f = fecha[:10]
    if vig_desde and f < vig_desde[:10]:
        return False
    if vig_hasta and f > vig_hasta[:10]:
        return False
    return True


def migrate_legacy_tarifas(db: Session) -> dict[str, int]:
    """Asigna version_id a tarifas sin versión (una activa legacy por proveedor)."""
    sin_version = list(
        db.scalars(select(Tarifa).where(Tarifa.version_id.is_(None))).all()
    )
    if not sin_version:
        return {}

    por_proveedor: dict[str, list[Tarifa]] = {}
    for t in sin_version:
        prov = normalizar_proveedor(t.proveedor) or _norm(t.proveedor)
        por_proveedor.setdefault(prov, []).append(t)

    creadas = 0
    for prov, filas in por_proveedor.items():
        ya_activa = db.scalar(
            select(TarifarioVersion.id).where(
                TarifarioVersion.proveedor == prov,
                TarifarioVersion.estado == "activa",
            )
        )
        if ya_activa:
            for t in filas:
                t.version_id = ya_activa
            continue

        vigencias = [t.vigencia_desde for t in filas if t.vigencia_desde]
        version = TarifarioVersion(
            proveedor=prov,
            vigencia_desde=max(vigencias) if vigencias else None,
            estado="activa",
            archivo_origen="legacy",
            filas_count=len(filas),
            notas="Migración automática de tarifas existentes",
            activated_at=datetime.utcnow(),
        )
        db.add(version)
        db.flush()
        for t in filas:
            t.version_id = version.id
        creadas += 1

    db.commit()
    return {p: len(f) for p, f in por_proveedor.items()}


def _persist_filas_version(
    db: Session,
    version: TarifarioVersion,
    rows: list[dict[str, Any]],
) -> int:
    count = 0
    for row in rows:
        precio = parse_money(row.get("precio"))
        if precio is None or not row.get("proveedor"):
            continue
        prov = normalizar_proveedor(str(row["proveedor"])) or str(row["proveedor"]).strip()
        tarifa = Tarifa(
            version_id=version.id,
            proveedor=prov,
            provincia=str(row.get("provincia") or "").strip(),
            localidad=str(row.get("localidad") or "").strip(),
            tipo_producto=str(row.get("tipo_producto") or "").strip(),
            medida=str(row.get("medida") or "").strip(),
            precio=precio,
            cedol=str(row["cedol"]).strip() if row.get("cedol") else None,
            vigencia_desde=str(row["vigencia_desde"]) if row.get("vigencia_desde") else None,
            vigencia_hasta=str(row["vigencia_hasta"]) if row.get("vigencia_hasta") else None,
            notas=str(row["notas"]) if row.get("notas") else None,
        )
        db.add(tarifa)
        count += 1
    version.filas_count = count
    return count


def crear_borrador_desde_filas(
    db: Session,
    *,
    proveedor: str,
    filas: list[dict[str, Any]],
    archivo_origen: str | None = None,
    hoja_origen: str | None = None,
    vigencia_desde: str | None = None,
    commit: bool = True,
) -> TarifarioVersion:
    prov = normalizar_proveedor(proveedor) or proveedor
    version = TarifarioVersion(
        proveedor=prov,
        vigencia_desde=vigencia_desde,
        estado="borrador",
        archivo_origen=archivo_origen,
        hoja_origen=hoja_origen,
    )
    db.add(version)
    db.flush()
    _persist_filas_version(db, version, filas)
    if commit:
        db.commit()
        db.refresh(version)
    return version


def _version_activa(db: Session, proveedor: str) -> TarifarioVersion | None:
    prov = normalizar_proveedor(proveedor) or proveedor
    return db.scalar(
        select(TarifarioVersion).where(
            TarifarioVersion.proveedor == prov,
            TarifarioVersion.estado == "activa",
        )
    )


def _tiene_version_activa(db: Session, proveedor: str) -> bool:
    return _version_activa(db, proveedor) is not None


def _mapa_desde_filas(filas: list[dict[str, Any]]) -> dict[tuple[str, str, str, str], float]:
    result: dict[tuple[str, str, str, str], float] = {}
    for row in filas:
        precio = parse_money(row.get("precio"))
        if precio is None or not row.get("proveedor"):
            continue
        key = _tarifa_key(
            str(row.get("provincia") or ""),
            str(row.get("localidad") or ""),
            str(row.get("tipo_producto") or ""),
            str(row.get("medida") or ""),
        )
        result[key] = precio
    return result


def _comparar_mapas(
    nuevo: dict[tuple[str, str, str, str], float],
    viejo: dict[tuple[str, str, str, str], float],
) -> dict[str, Any]:
    keys_nuevo = set(nuevo)
    keys_viejo = set(viejo)
    agregadas = keys_nuevo - keys_viejo
    eliminadas = keys_viejo - keys_nuevo
    modificadas = [k for k in keys_nuevo & keys_viejo if nuevo[k] != viejo[k]]
    return {
        "agregadas": len(agregadas),
        "eliminadas": len(eliminadas),
        "modificadas": len(modificadas),
        "sin_cambios": not agregadas and not eliminadas and not modificadas,
    }


def _es_igual_a_activa(
    db: Session,
    proveedor: str,
    filas: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any] | None]:
    activa = _version_activa(db, proveedor)
    if not activa:
        return False, None
    nuevo = _mapa_desde_filas(filas)
    viejo = _tarifas_de_version(db, activa.id)
    cmp = _comparar_mapas(nuevo, viejo)
    return cmp["sin_cambios"], cmp


def _ingestar_bloque_proveedor(
    db: Session,
    *,
    proveedor: str,
    filas: list[dict[str, Any]],
    archivo_origen: str,
    hoja_origen: str | None = None,
    vigencia_desde: str | None = None,
    auto_activar_si_sin_activa: bool = True,
    omitir_si_igual: bool = True,
    formato: str | None = None,
) -> tuple[dict[str, Any], int | None]:
    """
    Crea borrador o lo omite si los precios coinciden con la versión activa.
    Retorna (entry, version_id_auto_activada).
    """
    prov = normalizar_proveedor(proveedor) or proveedor

    if omitir_si_igual:
        igual, _cmp = _es_igual_a_activa(db, prov, filas)
        if igual:
            activa = _version_activa(db, prov)
            return (
                {
                    "proveedor": prov,
                    "archivo": archivo_origen,
                    "hoja": hoja_origen,
                    "omitido": True,
                    "motivo": "sin_cambios",
                    "activa_id": activa.id if activa else None,
                    "filas": len(_mapa_desde_filas(filas)),
                },
                None,
            )

    version = crear_borrador_desde_filas(
        db,
        proveedor=prov,
        filas=filas,
        archivo_origen=archivo_origen,
        hoja_origen=hoja_origen,
        vigencia_desde=vigencia_desde,
        commit=False,
    )
    entry: dict[str, Any] = {
        "version_id": version.id,
        "proveedor": version.proveedor,
        "archivo": archivo_origen,
        "hoja": hoja_origen,
        "filas": version.filas_count,
        "vigencia_desde": version.vigencia_desde,
        "estado": version.estado,
    }
    if formato:
        entry["formato"] = formato

    activada_id: int | None = None
    if auto_activar_si_sin_activa and not _tiene_version_activa(db, prov):
        activar_version(db, version.id, commit=False)
        entry["estado"] = "activa"
        entry["auto_activada"] = True
        activada_id = version.id
    return entry, activada_id


def escanear_carpeta_tarifarios(
    db: Session,
    folder: Path | None = None,
    *,
    auto_activar_si_sin_activa: bool = True,
) -> dict[str, Any]:
    """Lee data/tarifarios/*.xlsx y crea borradores por hoja/proveedor."""
    base = folder or TARIFARIOS_DIR
    if not base.exists():
        return {
            "carpeta": str(base),
            "borradores": [],
            "message": f"Carpeta no existe: {base}",
        }

    migrate_legacy_tarifas(db)
    borradores: list[dict[str, Any]] = []
    omitidos: list[dict[str, Any]] = []
    activadas_auto: list[int] = []

    for path in sorted(base.glob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        content = path.read_bytes()
        if is_tarifario_mantello(content):
            bloques = parse_tarifario_mantello_por_proveedor(content)
            for bloque in bloques:
                entry, act_id = _ingestar_bloque_proveedor(
                    db,
                    proveedor=bloque["proveedor"],
                    filas=bloque["filas"],
                    archivo_origen=path.name,
                    hoja_origen=bloque.get("hoja"),
                    vigencia_desde=bloque.get("vigencia_desde"),
                    auto_activar_si_sin_activa=auto_activar_si_sin_activa,
                )
                if entry.get("omitido"):
                    omitidos.append(entry)
                else:
                    borradores.append(entry)
                if act_id:
                    activadas_auto.append(act_id)
        else:
            from io import BytesIO

            import pandas as pd

            from app.services.tariff_service import TARIFA_COLUMNS, _resolve_precio_column

            df = pd.read_excel(BytesIO(content))
            df.columns = [str(c).strip().lower() for c in df.columns]
            col_precio = _resolve_precio_column(list(df.columns))
            parsed: list[dict] = []
            for _, row in df.iterrows():
                if not row.get("proveedor"):
                    continue
                payload = {k: row.get(k) for k in df.columns if k in TARIFA_COLUMNS}
                if col_precio and col_precio.lower() in df.columns:
                    payload["precio"] = row.get(col_precio.lower())
                parsed.append(payload)
            provs = {
                normalizar_proveedor(str(r.get("proveedor"))) or str(r["proveedor"])
                for r in parsed
                if r.get("proveedor")
            }
            for prov in provs:
                sub = [
                    r
                    for r in parsed
                    if (
                        normalizar_proveedor(str(r.get("proveedor")))
                        or str(r.get("proveedor"))
                    )
                    == prov
                ]
                entry, act_id = _ingestar_bloque_proveedor(
                    db,
                    proveedor=prov,
                    filas=sub,
                    archivo_origen=path.name,
                    auto_activar_si_sin_activa=auto_activar_si_sin_activa,
                    formato="tabla",
                )
                if entry.get("omitido"):
                    omitidos.append(entry)
                else:
                    borradores.append(entry)
                if act_id:
                    activadas_auto.append(act_id)

    db.commit()
    partes = [f"{len(borradores)} borrador(es) nuevo(s)"]
    if omitidos:
        provs_omit = ", ".join(o["proveedor"] for o in omitidos)
        partes.append(f"{len(omitidos)} sin cambios ({provs_omit})")
    if activadas_auto:
        partes.append(f"{len(activadas_auto)} activada(s) automáticamente")
    return {
        "carpeta": str(base),
        "borradores": borradores,
        "omitidos": omitidos,
        "activadas_auto": activadas_auto,
        "message": "Escaneo: " + ". ".join(partes) + ".",
    }


def importar_archivo_como_borrador(
    db: Session,
    content: bytes,
    filename: str,
) -> dict[str, Any]:
    migrate_legacy_tarifas(db)
    borradores: list[dict[str, Any]] = []
    omitidos: list[dict[str, Any]] = []
    activadas: list[int] = []

    if is_tarifario_mantello(content):
        bloques = parse_tarifario_mantello_por_proveedor(content)
    else:
        from io import BytesIO

        import pandas as pd

        from app.services.tariff_service import TARIFA_COLUMNS, _resolve_precio_column

        df = pd.read_excel(BytesIO(content))
        df.columns = [str(c).strip().lower() for c in df.columns]
        col_precio = _resolve_precio_column(list(df.columns))
        rows: list[dict] = []
        for _, row in df.iterrows():
            if not row.get("proveedor"):
                continue
            payload = {k: row.get(k) for k in df.columns if k in TARIFA_COLUMNS}
            if col_precio and col_precio.lower() in df.columns:
                payload["precio"] = row.get(col_precio.lower())
            rows.append(payload)
        provs = {
            normalizar_proveedor(str(r.get("proveedor"))) or str(r["proveedor"])
            for r in rows
            if r.get("proveedor")
        }
        bloques = [
            {
                "proveedor": prov,
                "filas": [
                    r
                    for r in rows
                    if (
                        normalizar_proveedor(str(r.get("proveedor")))
                        or str(r.get("proveedor"))
                    )
                    == prov
                ],
            }
            for prov in provs
        ]

    for bloque in bloques:
        entry, act_id = _ingestar_bloque_proveedor(
            db,
            proveedor=bloque["proveedor"],
            filas=bloque["filas"],
            archivo_origen=filename,
            hoja_origen=bloque.get("hoja"),
            vigencia_desde=bloque.get("vigencia_desde"),
        )
        if entry.get("omitido"):
            omitidos.append(entry)
        else:
            borradores.append(entry)
        if act_id:
            activadas.append(act_id)

    db.commit()
    if not bloques:
        return {
            "borradores": [],
            "omitidos": [],
            "activadas_auto": [],
            "message": (
                "No se reconocieron tarifas en el Excel. "
                "Usá el Mantello (hojas clicpaq/fransof/…) o una matriz provincial "
                "tipo Bedtime/Wamaro (provincia + CEDOL + precios)."
            ),
        }
    if omitidos and not borradores:
        msg = f"Sin cambios: {', '.join(o['proveedor'] for o in omitidos)} ya coincide con la versión activa."
    elif omitidos:
        msg = (
            f"{len(borradores)} borrador(es). "
            f"Omitidos (sin cambios): {', '.join(o['proveedor'] for o in omitidos)}."
        )
    else:
        msg = f"Se crearon {len(borradores)} borrador(es)."
    return {
        "borradores": borradores,
        "omitidos": omitidos,
        "activadas_auto": activadas,
        "message": msg,
    }


def _tarifas_de_version(db: Session, version_id: int) -> dict[tuple, float]:
    filas = db.scalars(select(Tarifa).where(Tarifa.version_id == version_id)).all()
    return {
        _tarifa_key(t.provincia, t.localidad, t.tipo_producto, t.medida): t.precio
        for t in filas
    }


def diff_version(db: Session, version_id: int, *, max_muestra: int = 30) -> dict[str, Any]:
    version = db.get(TarifarioVersion, version_id)
    if not version:
        return {"error": "Versión no encontrada"}

    activa = db.scalar(
        select(TarifarioVersion).where(
            TarifarioVersion.proveedor == version.proveedor,
            TarifarioVersion.estado == "activa",
        )
    )
    nuevo = _tarifas_de_version(db, version_id)
    if not activa or activa.id == version_id:
        return {
            "version_id": version_id,
            "proveedor": version.proveedor,
            "sin_activa_previa": activa is None or activa.id == version_id,
            "filas_nuevas": len(nuevo),
            "agregadas": len(nuevo),
            "eliminadas": 0,
            "modificadas": 0,
            "muestra_cambios": [],
        }

    viejo = _tarifas_de_version(db, activa.id)
    cmp = _comparar_mapas(nuevo, viejo)
    keys_nuevo = set(nuevo)
    keys_viejo = set(viejo)
    agregadas = keys_nuevo - keys_viejo
    eliminadas = keys_viejo - keys_nuevo
    modificadas = [k for k in keys_nuevo & keys_viejo if nuevo[k] != viejo[k]]

    muestra = []
    for k in list(modificadas)[:max_muestra]:
        muestra.append(
            {
                "provincia": k[0],
                "localidad": k[1],
                "tipo": k[2],
                "medida": k[3],
                "precio_anterior": viejo[k],
                "precio_nuevo": nuevo[k],
                "delta": round(nuevo[k] - viejo[k], 2),
            }
        )
    for k in list(agregadas)[: max(0, max_muestra - len(muestra))]:
        muestra.append(
            {
                "provincia": k[0],
                "localidad": k[1],
                "tipo": k[2],
                "medida": k[3],
                "precio_anterior": None,
                "precio_nuevo": nuevo[k],
                "delta": None,
                "tipo_cambio": "nueva",
            }
        )

    return {
        "version_id": version_id,
        "proveedor": version.proveedor,
        "activa_id": activa.id,
        "vigencia_desde": version.vigencia_desde,
        "activa_vigencia": activa.vigencia_desde,
        "filas_nuevas": len(nuevo),
        "filas_activas": len(viejo),
        "agregadas": cmp["agregadas"],
        "eliminadas": cmp["eliminadas"],
        "modificadas": cmp["modificadas"],
        "sin_cambios": cmp["sin_cambios"],
        "muestra_cambios": muestra,
    }


def activar_version(
    db: Session,
    version_id: int,
    *,
    vigencia_desde: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    version = db.get(TarifarioVersion, version_id)
    if not version:
        return {"error": "Versión no encontrada"}
    if version.estado == "activa":
        return {"version_id": version_id, "message": "Ya estaba activa"}

    anterior = _version_activa(db, version.proveedor)
    if anterior and anterior.id != version_id:
        cmp = _comparar_mapas(
            _tarifas_de_version(db, version_id),
            _tarifas_de_version(db, anterior.id),
        )
        if cmp["sin_cambios"]:
            db.execute(delete(Tarifa).where(Tarifa.version_id == version_id))
            db.delete(version)
            if commit:
                db.commit()
            return {
                "version_id": version_id,
                "proveedor": version.proveedor,
                "omitido": True,
                "sin_cambios": True,
                "message": (
                    f"{version.proveedor}: sin cambios respecto a la versión activa "
                    f"(v{anterior.id}). No se renovó."
                ),
            }

    if vigencia_desde:
        version.vigencia_desde = vigencia_desde[:10]

    if anterior:
        anterior.estado = "historica"
        anterior.vigencia_hasta = version.vigencia_desde

    version.estado = "activa"
    version.activated_at = datetime.utcnow()
    if commit:
        db.commit()
    return {
        "version_id": version_id,
        "proveedor": version.proveedor,
        "filas": version.filas_count,
        "reemplaza_id": anterior.id if anterior else None,
        "message": f"Versión activa para {version.proveedor}",
    }


def rollback_proveedor(db: Session, proveedor: str) -> dict[str, Any]:
    prov = normalizar_proveedor(proveedor) or proveedor
    activa = db.scalar(
        select(TarifarioVersion).where(
            TarifarioVersion.proveedor == prov,
            TarifarioVersion.estado == "activa",
        )
    )
    if not activa:
        return {"error": f"No hay versión activa para {prov}"}

    anterior = db.scalar(
        select(TarifarioVersion)
        .where(
            TarifarioVersion.proveedor == prov,
            TarifarioVersion.estado == "historica",
        )
        .order_by(TarifarioVersion.activated_at.desc().nullslast(), TarifarioVersion.id.desc())
    )
    if not anterior:
        return {"error": "No hay versión histórica para rollback"}

    activa.estado = "historica"
    anterior.estado = "activa"
    anterior.activated_at = datetime.utcnow()
    anterior.vigencia_hasta = None
    db.commit()
    return {
        "proveedor": prov,
        "activa_id": anterior.id,
        "archivada_id": activa.id,
        "message": f"Rollback: {prov} → versión {anterior.id}",
    }


def descartar_borrador(db: Session, version_id: int) -> dict[str, Any]:
    version = db.get(TarifarioVersion, version_id)
    if not version:
        return {"error": "Versión no encontrada"}
    if version.estado != "borrador":
        return {"error": "Solo se pueden descartar borradores"}

    db.execute(delete(Tarifa).where(Tarifa.version_id == version_id))
    db.delete(version)
    db.commit()
    return {"version_id": version_id, "message": "Borrador descartado"}


def _version_mejor_para_fecha(
    candidatas: list[TarifarioVersion],
    fecha: str,
) -> TarifarioVersion | None:
    """Elige la versión vigente para una fecha (con fallback a la anterior más cercana)."""
    if not candidatas:
        return None

    f = fecha[:10]
    en_rango = [
        v
        for v in candidatas
        if _fecha_en_vigencia(v.vigencia_desde, v.vigencia_hasta, f)
    ]
    if en_rango:
        activas = [v for v in en_rango if v.estado == "activa"]
        pool = activas or en_rango
        return max(
            pool,
            key=lambda v: (
                v.vigencia_desde or "",
                v.activated_at or datetime.min,
                v.id,
            ),
        )

    anteriores = [
        v
        for v in candidatas
        if not v.vigencia_desde or v.vigencia_desde[:10] <= f
    ]
    if anteriores:
        return max(
            anteriores,
            key=lambda v: (
                v.vigencia_desde or "",
                v.activated_at or datetime.min,
                v.id,
            ),
        )

    return min(
        candidatas,
        key=lambda v: (v.vigencia_desde or "9999-12-31", v.id),
    )


def ids_versiones_vigentes(db: Session, fecha: str | None = None) -> set[int]:
    """IDs de versiones a usar en lookup (activas o históricas según fecha del envío)."""
    if not fecha:
        activas = db.scalars(
            select(TarifarioVersion.id).where(TarifarioVersion.estado == "activa")
        ).all()
        ids = set(activas)
        if ids:
            return ids
        return set()

    versiones = list(
        db.scalars(
            select(TarifarioVersion).where(TarifarioVersion.estado != "borrador")
        ).all()
    )
    por_proveedor: dict[str, list[TarifarioVersion]] = {}
    for v in versiones:
        por_proveedor.setdefault(v.proveedor, []).append(v)

    ids: set[int] = set()
    for _prov, cand in por_proveedor.items():
        elegida = _version_mejor_para_fecha(cand, fecha)
        if elegida:
            ids.add(elegida.id)
    return ids


def tarifas_activas(db: Session, fecha: str | None = None) -> list[Tarifa]:
    """Tarifas de versiones vigentes (solo activas si no hay fecha)."""
    version_ids = ids_versiones_vigentes(db, fecha)
    if version_ids:
        return list(
            db.scalars(select(Tarifa).where(Tarifa.version_id.in_(version_ids))).all()
        )
    # Legacy sin migrar
    return list(db.scalars(select(Tarifa).where(Tarifa.version_id.is_(None))).all())


class TarifarioContext:
    """
    Cache de tarifas por fecha de referencia.
    Usar al calcular cobro/proveedor/maestro para respetar el tarifario del período.
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._cache: dict[str | None, list[Tarifa]] = {}

    def tarifas_para_fecha(self, fecha: str | None) -> list[Tarifa]:
        key = fecha[:10] if fecha else None
        if key not in self._cache:
            self._cache[key] = tarifas_activas(self._db, key)
        return self._cache[key]

    def tarifas_para_envio(self, envio: Envio) -> list[Tarifa]:
        from app.services.fecha_utils import fecha_referencia_tarifa

        return self.tarifas_para_fecha(fecha_referencia_tarifa(envio))

    def tarifas_para_grupo(self, lineas: list[Envio]) -> list[Tarifa]:
        if not lineas:
            return self.tarifas_para_fecha(None)
        return self.tarifas_para_envio(lineas[0])

    def tarifas_actuales(self) -> list[Tarifa]:
        return self.tarifas_para_fecha(None)

    def snapshot_versiones(self, fecha: str | None) -> dict[str, int]:
        """Proveedor → id de versión vigente en esa fecha."""
        if not fecha:
            versiones = list(
                self._db.scalars(
                    select(TarifarioVersion).where(TarifarioVersion.estado == "activa")
                ).all()
            )
        else:
            ids = ids_versiones_vigentes(self._db, fecha)
            versiones = [
                v
                for v in self._db.scalars(select(TarifarioVersion)).all()
                if v.id in ids
            ]
        return {v.proveedor: v.id for v in versiones}

    def versiones_para_fecha(self, fecha: str | None) -> list[dict[str, Any]]:
        """Resumen de qué versión usa cada proveedor en una fecha (debug/UI)."""
        if not fecha:
            versiones = list(
                self._db.scalars(
                    select(TarifarioVersion).where(TarifarioVersion.estado == "activa")
                ).all()
            )
        else:
            ids = ids_versiones_vigentes(self._db, fecha)
            versiones = [
                v
                for v in self._db.scalars(select(TarifarioVersion)).all()
                if v.id in ids
            ]
        return [_version_to_dict(v) for v in versiones]


def listar_estado(db: Session) -> dict[str, Any]:
    migrate_legacy_tarifas(db)
    cadencia = _cargar_cadencia()
    proveedores: list[dict[str, Any]] = []

    for prov in PROVEEDORES_VERSIONADOS:
        activa = db.scalar(
            select(TarifarioVersion).where(
                TarifarioVersion.proveedor == prov,
                TarifarioVersion.estado == "activa",
            )
        )
        borradores = list(
            db.scalars(
                select(TarifarioVersion)
                .where(
                    TarifarioVersion.proveedor == prov,
                    TarifarioVersion.estado == "borrador",
                )
                .order_by(TarifarioVersion.created_at.desc())
            ).all()
        )
        historico = db.scalar(
            select(func.count())
            .select_from(TarifarioVersion)
            .where(
                TarifarioVersion.proveedor == prov,
                TarifarioVersion.estado == "historica",
            )
        )
        proveedores.append(
            {
                "proveedor": prov,
                "label": PROVEEDOR_LABELS.get(prov, prov),
                "cadencia": cadencia.get(prov, {}),
                "activa": _version_to_dict(activa) if activa else None,
                "borradores": [_version_to_dict(b) for b in borradores],
                "versiones_historicas": historico or 0,
            }
        )

    return {
        "carpeta_tarifarios": str(TARIFARIOS_DIR),
        "proveedores": proveedores,
    }


def _version_to_dict(v: TarifarioVersion) -> dict[str, Any]:
    return {
        "id": v.id,
        "proveedor": v.proveedor,
        "estado": v.estado,
        "vigencia_desde": v.vigencia_desde,
        "vigencia_hasta": v.vigencia_hasta,
        "archivo_origen": v.archivo_origen,
        "hoja_origen": v.hoja_origen,
        "filas_count": v.filas_count,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "activated_at": v.activated_at.isoformat() if v.activated_at else None,
        "notas": v.notas,
    }


def listar_versiones(
    db: Session,
    proveedor: str | None = None,
    estado: str | None = None,
) -> list[dict[str, Any]]:
    q = select(TarifarioVersion).order_by(TarifarioVersion.id.desc())
    if proveedor:
        prov = normalizar_proveedor(proveedor) or proveedor
        q = q.where(TarifarioVersion.proveedor == prov)
    if estado:
        q = q.where(TarifarioVersion.estado == estado)
    return [_version_to_dict(v) for v in db.scalars(q).all()]
