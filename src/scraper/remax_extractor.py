"""
Extractor específico de RE/MAX.

RE/MAX (Angular) embebe el estado completo de la publicación —incluyendo
precio, expensas, dirección y coordenadas ya calculadas— en un
<script id="ng-state" type="application/json"> (TransferState de Angular
Universal para SSR). Esto es mucho más rico que el JSON-LD/meta genérico.

IMPORTANTE (corregido tras revisión del piloto v1): esto NO es JSON-LD
schema.org — es un formato propio de RE/MAX. Se etiqueta explícitamente
como fuente "REMAX_NG_STATE", nunca como "JSON_LD", para no mezclar
niveles de confianza/formato distintos en la trazabilidad.
"""

import json
from typing import Optional
from bs4 import BeautifulSoup

from datetime import date

# Claves del ng-state que NO son el listado (son datos globales de la app)
_STATIC_KEYS = {"transfer-translate-es-AR", "subdomain-owner", "__nghData__"}

TYPE_MAP = {
    "casa": "Casa",
    "departamento": "Departamento",
    "departamento_duplex": "Duplex",
    "ph": "PH",
    "terreno": "Terreno",
    "local": "Local Comercial",
    "oficina": "Oficina",
}

FUENTE = "REMAX_NG_STATE"


def extract_ng_state_listing(html: str) -> Optional[dict]:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="ng-state")
    if not tag or not tag.string:
        return None

    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError:
        return None

    listing_keys = [k for k in data.keys() if k not in _STATIC_KEYS]
    for key in listing_keys:
        node = data.get(key, {})
        listing = node.get("b", {}).get("data") if isinstance(node, dict) else None
        if isinstance(listing, dict) and "price" in listing:
            return listing

    return None


def build_remax_fields(fetch_result) -> dict:
    """
    Devuelve un dict con los mismos nombres de campo que usa
    record_builder, listo para hacer .update() sobre lo que ya extrajo
    el pipeline genérico (JSON-LD/meta), sin perder lo genérico como
    fallback si ng-state no está presente.
    """
    listing = extract_ng_state_listing(fetch_result.html)
    if not listing:
        return {}

    out: dict = {}

    out["titulo_publicacion"] = listing.get("title")
    out["titulo_publicacion_fuente"] = FUENTE if listing.get("title") else None

    out["descripcion_publicacion"] = listing.get("description")
    out["descripcion_publicacion_fuente"] = FUENTE if listing.get("description") else None

    if listing.get("price") is not None:
        out["precio"] = listing["price"]
        out["moneda"] = (listing.get("currency") or {}).get("value")
        out["precio_fuente"] = FUENTE

    if listing.get("expensesPrice") is not None:
        out["expensas"] = listing["expensesPrice"]
        out["expensas_fuente"] = FUENTE

    # Dirección estructurada del sitio: displayAddress suele ser "Calle Numero".
    # Se guarda como candidato "address_structured", NO se asume verdadero
    # sin contrastar contra el texto de la descripción (eso lo hace
    # record_builder con address_text_parser + conflict_utils).
    if listing.get("displayAddress"):
        out["direccion_texto"] = listing["displayAddress"]
        out["direccion_fuente"] = FUENTE

    if listing.get("bedrooms") is not None:
        out["dormitorios"] = listing["bedrooms"]
    if listing.get("bathrooms") is not None:
        out["banos"] = listing["bathrooms"]
    if listing.get("totalRooms") is not None:
        out["ambientes"] = listing["totalRooms"]

    for campo_origen, campo_destino in [
        ("dimensionTotalBuilt", "superficie_total_m2"),
        ("dimensionCovered", "superficie_cubierta_m2"),
        ("dimensionUncovered", "superficie_descubierta_m2"),
    ]:
        valor = listing.get(campo_origen)
        if valor not in (None, 0):
            out[campo_destino] = valor
    if "superficie_total_m2" in out:
        out["superficie_total_fuente"] = FUENTE
        out["superficie_total_confidence"] = "ESTRUCTURADO_ALTA_CONFIANZA"

    # Año de construcción (NO "antigüedad" — son cosas distintas, ver
    # property_normalizer.normalize_antiguedad). Se calcula la antigüedad
    # en años a partir de la fecha real, no se guarda el año suelto.
    if listing.get("yearBuilt"):
        anio = listing["yearBuilt"]
        out["anio_construccion"] = anio
        out["antiguedad_anios"] = max(0, date.today().year - anio)
        out["antiguedad_fuente"] = FUENTE

    # apto_credito: se preserva el valor CRUDO (True/False), sin
    # colapsar False a None — el conflicto contra el texto de la
    # descripción se resuelve después, en record_builder.
    if listing.get("aptCredit") is not None:
        out["apto_credito_structured"] = bool(listing["aptCredit"])
    if listing.get("professionalUse") is not None:
        out["apto_profesional"] = bool(listing["professionalUse"]) or None
    if listing.get("parkingSpaces"):
        out["cochera"] = True

    tipo_raw = (listing.get("type") or {}).get("value")
    if tipo_raw:
        out["tipo_texto"] = TYPE_MAP.get(tipo_raw, tipo_raw)
        out["tipo_fuente"] = FUENTE

    # Coordenadas: RE/MAX ya las calcula. NO se afirma que sean "exactas"
    # solo por venir del sitio — record_builder las contrasta contra la
    # dirección resuelta y las marca como precisión "SITE_PROVIDED".
    location = listing.get("location") or {}
    coords = location.get("coordinates")
    if coords and len(coords) == 2:
        out["latitude_fuente_sitio"] = coords[1]
        out["longitude_fuente_sitio"] = coords[0]
        out["coordinates_source"] = FUENTE

    return out
