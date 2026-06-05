"""Geocoding y distancia sucursal → domicilio (portado desde mantello-project)."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from app.config import DATA_DIR

CACHE_DB = DATA_DIR / "kilometrizador_cache.db"


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    h = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


@dataclass
class GeoPoint:
    lat: float
    lon: float
    label: str = ""
    source: str = ""


class Kilometrizador:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or CACHE_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._nominatim_lock = threading.Lock()
        self._nominatim_last_call = 0.0
        self._suggest_cache_lock = threading.Lock()
        self._suggest_cache: dict[tuple[str, int], tuple[float, list[GeoPoint]]] = {}

    def _ua(self) -> str:
        return os.getenv("FLETES_NOMINATIM_UA", "control-fletes-kilometrizador/1.0")

    def _nominatim_throttle(self, *, wait_for_slot: bool) -> bool:
        min_interval_s = float(os.getenv("NOMINATIM_MIN_INTERVAL_S", "1.1"))
        now = time.monotonic()
        with self._nominatim_lock:
            next_allowed = self._nominatim_last_call + min_interval_s
            sleep_s = next_allowed - now
            if sleep_s > 0 and not wait_for_slot:
                return False
            self._nominatim_last_call = max(now, next_allowed)
        if sleep_s > 0:
            time.sleep(sleep_s)
        return True

    def _nominatim_get(
        self,
        params: dict[str, Any],
        *,
        timeout_s: float = 12,
        retries: int = 1,
        throttle_wait: bool = True,
    ) -> list:
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            if not self._nominatim_throttle(wait_for_slot=throttle_wait):
                return []
            try:
                resp = requests.get(
                    "https://nominatim.openstreetmap.org/search",
                    params=params,
                    headers={"User-Agent": self._ua()},
                    timeout=timeout_s,
                )
                if resp.status_code == 429:
                    time.sleep(min(1.5 * (attempt + 1), 3.0))
                    continue
                resp.raise_for_status()
                return resp.json() or []
            except Exception as e:
                last_err = e
                time.sleep(min(1.5 * (attempt + 1), 3.0))
        if last_err:
            raise RuntimeError(str(last_err))
        return []

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS geocode_cache (
                  key TEXT PRIMARY KEY,
                  query TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  lat REAL NOT NULL,
                  lon REAL NOT NULL,
                  label TEXT,
                  raw_json TEXT,
                  created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS route_cache (
                  key TEXT PRIMARY KEY,
                  provider TEXT NOT NULL,
                  o_lat REAL NOT NULL,
                  o_lon REAL NOT NULL,
                  d_lat REAL NOT NULL,
                  d_lon REAL NOT NULL,
                  distance_km REAL NOT NULL,
                  duration_s REAL,
                  raw_json TEXT,
                  created_at TEXT NOT NULL
                )
                """
            )

    def _key(self, *parts: str) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(p.encode("utf-8"))
            h.update(b"\0")
        return h.hexdigest()

    def geocode(self, query: str) -> GeoPoint:
        q0 = (query or "").strip()
        if not q0:
            raise ValueError("Destino vacío")
        q0 = re.sub(r"\bC\.A\.B\.A\.?\b", "CABA", q0, flags=re.IGNORECASE)
        if "argentina" not in q0.lower():
            q0 = f"{q0}, Argentina"
        provider = "ors" if os.getenv("ORS_API_KEY") else "nominatim"
        key = self._key("geocode", provider, q0.lower())
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT lat, lon, label FROM geocode_cache WHERE key = ?",
                (key,),
            ).fetchone()
            if row:
                return GeoPoint(lat=row[0], lon=row[1], label=row[2] or q0, source=f"cache:{provider}")

        arr = self._nominatim_get(
            {
                "q": q0,
                "format": "json",
                "limit": 1,
                "countrycodes": "ar",
                "addressdetails": 1,
            },
            throttle_wait=True,
        )
        if not arr:
            raise ValueError(f"No se pudo geocodificar: {query}")
        item = arr[0]
        point = GeoPoint(
            lat=float(item["lat"]),
            lon=float(item["lon"]),
            label=item.get("display_name", q0),
            source=provider,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO geocode_cache(key, query, provider, lat, lon, label, raw_json, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    key,
                    q0,
                    provider,
                    point.lat,
                    point.lon,
                    point.label,
                    json.dumps(item, ensure_ascii=False),
                    datetime.now().isoformat(),
                ),
            )
        return point

    def route(self, origin: GeoPoint, dest: GeoPoint) -> dict[str, Any]:
        provider = "ors" if os.getenv("ORS_API_KEY") else "haversine"
        o_lat, o_lon = round(origin.lat, 6), round(origin.lon, 6)
        d_lat, d_lon = round(dest.lat, 6), round(dest.lon, 6)
        key = self._key("route", provider, str(o_lat), str(o_lon), str(d_lat), str(d_lon))
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT distance_km, duration_s FROM route_cache WHERE key = ?",
                (key,),
            ).fetchone()
            if row and float(row[0] or 0) > 0:
                return {
                    "provider": provider,
                    "source": "cache",
                    "distance_km": row[0],
                    "duration_s": row[1],
                }

        if provider == "ors" and os.getenv("ORS_API_KEY"):
            api_key = os.getenv("ORS_API_KEY")
            base = (os.getenv("ORS_BASE_URL") or "https://api.openrouteservice.org").rstrip("/")
            resp = requests.post(
                f"{base}/v2/directions/driving-car",
                json={"coordinates": [[o_lon, o_lat], [d_lon, d_lat]]},
                headers={"Authorization": api_key, "Content-Type": "application/json"},
                timeout=float(os.getenv("ORS_TIMEOUT_S", "25")),
            )
            resp.raise_for_status()
            data = resp.json()
            distance_m = 0.0
            if isinstance(data.get("routes"), list) and data["routes"]:
                summary = (data["routes"][0] or {}).get("summary") or {}
                distance_m = float(summary.get("distance") or 0.0)
            distance_km = distance_m / 1000.0
            raw_json = json.dumps(data, ensure_ascii=False)
            duration_s = None
        else:
            distance_km = haversine_km((o_lat, o_lon), (d_lat, d_lon))
            raw_json = None
            duration_s = None

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO route_cache(key, provider, o_lat, o_lon, d_lat, d_lon, distance_km, duration_s, raw_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    provider,
                    o_lat,
                    o_lon,
                    d_lat,
                    d_lon,
                    distance_km,
                    duration_s,
                    raw_json,
                    datetime.now().isoformat(),
                ),
            )
        return {
            "provider": provider,
            "source": "live",
            "distance_km": distance_km,
            "duration_s": duration_s,
        }


_kilometrizador: Kilometrizador | None = None


def get_kilometrizador() -> Kilometrizador:
    global _kilometrizador
    if _kilometrizador is None:
        _kilometrizador = Kilometrizador()
    return _kilometrizador
