"""
Extractor específico de MercadoLibre Inmuebles.

MercadoLibre expone muy poco en el JSON-LD "Product" (solo precio), pero
SÍ trae un JSON-LD "BreadcrumbList" con la jerarquía tipo -> operación ->
región -> partido -> localidad, ya limpia. Es la fuente más confiable de
tipo/localidad/partido para este dominio (36% del dataset).
"""

from typing import Optional


def _find_breadcrumb(jsonld: list) -> Optional[list]:
    for block in jsonld:
        if block.get("@type") == "BreadcrumbList":
            return block.get("itemListElement", [])
    return None


def build_mercadolibre_fields(fetch_result) -> dict:
    items = _find_breadcrumb(fetch_result.jsonld)
    if not items:
        return {}

    nombres = [it.get("item", {}).get("name") for it in sorted(items, key=lambda x: x.get("position", 0))]
    nombres = [n for n in nombres if n]

    if not nombres:
        return {}

    out = {}

    # Primer nivel util (posicion 2, ya que la 1 siempre es "Inmuebles")
    # suele ser el tipo de propiedad: PH / Casa / Departamento / etc.
    if len(nombres) >= 2:
        out["tipo_texto"] = nombres[1]
        out["tipo_fuente"] = "JSON_LD"

    # El último nivel geográfico del breadcrumb es la localidad/barrio más
    # específico (ej: "Lanús Este"). No hace falta tomar el partido del
    # nivel anterior a mano: address_normalizer.normalize_localidad_o_caba
    # ya sabe derivar el partido correcto a partir de la localidad.
    geograficos = nombres[3:] if len(nombres) > 3 else nombres[2:]
    if geograficos:
        out["localidad_texto"] = geograficos[-1]

    if out.get("localidad_texto"):
        out["localidad_fuente"] = "JSON_LD"

    return out
