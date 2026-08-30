"""
Control de calidad geográfica de las coordenadas devueltas por el
geocodificador. Nunca se acepta una coordenada solo porque el proveedor
devolvió HTTP 200: se valida que caiga dentro de Argentina y, cuando es
posible, que coincida con la provincia esperada.
"""

import unicodedata
from typing import Optional

# Bounding box aproximado de Argentina continental + islas (laxo a propósito)
ARGENTINA_BBOX = {"lat_min": -55.1, "lat_max": -21.7, "lon_min": -73.6, "lon_max": -53.5}

PROVINCIA_SYNONYMS = {
    "buenos aires": "buenos aires",
    "ciudad autonoma de buenos aires": "ciudad autonoma de buenos aires",
    "caba": "ciudad autonoma de buenos aires",
}


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower().strip()


def is_within_argentina(lat: float, lon: float) -> bool:
    return (
        ARGENTINA_BBOX["lat_min"] <= lat <= ARGENTINA_BBOX["lat_max"]
        and ARGENTINA_BBOX["lon_min"] <= lon <= ARGENTINA_BBOX["lon_max"]
    )


def validate_coordinates(
    lat: float, lon: float, provincia_esperada: Optional[str], raw_address: dict
) -> tuple[bool, str]:
    if not is_within_argentina(lat, lon):
        return False, "fuera_de_argentina"

    if provincia_esperada:
        esperada = _clean(provincia_esperada)
        esperada = PROVINCIA_SYNONYMS.get(esperada, esperada)

        devuelta = _clean(raw_address.get("state") or raw_address.get("province") or "")
        devuelta = PROVINCIA_SYNONYMS.get(devuelta, devuelta)

        if devuelta and esperada and devuelta != esperada:
            # CABA vs Buenos Aires es el caso límite más frecuente: si el
            # geocoder dice CABA pero esperábamos Buenos Aires (o viceversa)
            # y la propiedad está en zona límite (ej. Avellaneda/Lanús),
            # lo dejamos pasar como advertencia pero no lo descartamos del
            # todo salvo que sea una provincia totalmente distinta.
            provincias_grandes = {"buenos aires", "ciudad autonoma de buenos aires"}
            if not (esperada in provincias_grandes and devuelta in provincias_grandes):
                return False, f"provincia_no_coincide (esperada={esperada}, obtenida={devuelta})"

    return True, "ok"


def detect_generic_coordinate_reuse(records: list[dict], min_repetitions: int = 5) -> list[tuple[tuple, int]]:
    """
    Detecta coordenadas que se repiten demasiadas veces (indicio de
    geocodificación a nivel ciudad/centroide genérico en vez de dirección
    real). Devuelve [(coord, cantidad), ...] para las que superan el umbral.
    """
    from collections import Counter

    coords = [
        (r["latitude"], r["longitude"])
        for r in records
        if r.get("latitude") is not None and r.get("longitude") is not None
    ]
    counts = Counter(coords)
    return [(coord, n) for coord, n in counts.items() if n >= min_repetitions]
