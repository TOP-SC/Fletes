import re

_RE_X = re.compile(r"^\s*X\d", re.IGNORECASE)
_RE_RAR = re.compile(r"^\s*RAR\s*[\d\-]+", re.IGNORECASE)


def es_remito_transito(remito: str | None) -> bool:
    """Remitos X = tránsito interno; no son el remito del CD al cliente."""
    if not remito:
        return False
    t = str(remito).strip().upper()
    if _RE_X.match(t):
        return True
    return t.startswith("X") and bool(re.search(r"\d{5,}", t))


def es_remito_oficial(remito: str | None) -> bool:
    """Remito válido del CD (RAR … o R-00… / R00178…). Nunca X, pedido ni COD artículo."""
    if not remito or es_remito_transito(remito):
        return False
    t = str(remito).strip()
    if _RE_RAR.match(t):
        return True
    clean = re.sub(r"[\s\-\./]", "", t.upper())
    # Solo dígitos largos = suele ser NRO PEDIDO mal mapeado, no remito
    if re.match(r"^\d{10,}$", clean):
        return False
    if re.match(r"^R\d{10,}", clean):
        return True
    if re.match(r"^RAR\d{8,}", clean):
        return True
    return False


def normalizar_remito(remito: str | None) -> str:
    """
    Clave de cruce Clickpack ↔ Tango.
    Tango: R0017800318022 — Clickpack: 17800318022 (sin R ni ceros leading).
    También acepta cuerpos solo-dígitos (Franzof sin guiones / sin prefijo R).
    """
    if not remito or es_remito_transito(remito):
        return ""
    text = str(remito).strip().upper()
    text = re.sub(r"[\s\-\./]", "", text)
    # Franzof / planillas: remito como solo dígitos (8–14) = cuerpo del R…
    if re.match(r"^\d{8,14}$", text):
        return text.lstrip("0") or text
    if not es_remito_oficial(remito):
        return ""
    if text.startswith("RAR"):
        text = text[3:]
    elif text.startswith("R"):
        text = text[1:]
    digits = re.sub(r"\D", "", text)
    if not digits:
        return text
    normalized = digits.lstrip("0") or digits
    return normalized
