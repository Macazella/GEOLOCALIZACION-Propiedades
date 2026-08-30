"""
Extracción genérica de campos crudos a partir de lo que devuelve
base_scraper.fetch() (JSON-LD, meta tags, HTML). Válida para la mayoría
de sitios que usan schema.org (RealEstateListing/Product/Offer) y
OpenGraph, que es el caso típico de RE/MAX, MercadoLibre y BuscadorProp.

Cada campo devuelto viene acompañado de su "_fuente" (JSON_LD, META,
TEXTO_PUBLICACION) para trazabilidad.
"""

from typing import Optional
from bs4 import BeautifulSoup


def _first(*values):
    for v in values:
        if v not in (None, "", []):
            return v
    return None


def _jsonld_get(jsonld_blocks: list, *keys: str):
    """Busca la primera clave presente (soporta anidamiento con '.')."""
    for block in jsonld_blocks:
        node = block
        for key_path in keys:
            value = block
            for part in key_path.split("."):
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
                    break
            if value not in (None, ""):
                return value
    return None


def extract_titulo(jsonld: list, meta: dict, soup: Optional[BeautifulSoup]) -> dict:
    valor = _jsonld_get(jsonld, "name", "headline")
    if valor:
        return {"titulo_publicacion": valor, "titulo_publicacion_fuente": "JSON_LD"}

    valor = meta.get("og:title") or meta.get("twitter:title")
    if valor:
        return {"titulo_publicacion": valor, "titulo_publicacion_fuente": "META"}

    if soup and soup.title and soup.title.string:
        return {"titulo_publicacion": soup.title.string.strip(), "titulo_publicacion_fuente": "TEXTO_PUBLICACION"}

    return {"titulo_publicacion": None, "titulo_publicacion_fuente": None}


def extract_descripcion(jsonld: list, meta: dict) -> dict:
    valor = _jsonld_get(jsonld, "description")
    if valor:
        return {"descripcion_publicacion": valor, "descripcion_publicacion_fuente": "JSON_LD"}

    valor = meta.get("og:description") or meta.get("description")
    if valor:
        return {"descripcion_publicacion": valor, "descripcion_publicacion_fuente": "META"}

    return {"descripcion_publicacion": None, "descripcion_publicacion_fuente": None}


def extract_precio_texto(jsonld: list, meta: dict) -> dict:
    """
    Devuelve un texto candidato para que property_normalizer.normalize_precio
    lo parsee (moneda + monto), junto con su fuente. No parsea acá el
    número para no duplicar lógica de normalización.
    """
    price = _jsonld_get(jsonld, "offers.price", "offers.priceSpecification.price")
    currency = _jsonld_get(jsonld, "offers.priceCurrency", "offers.priceSpecification.priceCurrency")
    if price:
        texto = f"{currency or ''} {price}".strip()
        return {"precio_texto": texto, "precio_fuente": "JSON_LD"}

    price_amount_meta = meta.get("product:price:amount") or meta.get("og:price:amount")
    currency_meta = meta.get("product:price:currency") or meta.get("og:price:currency")
    if price_amount_meta:
        texto = f"{currency_meta or ''} {price_amount_meta}".strip()
        return {"precio_texto": texto, "precio_fuente": "META"}

    return {"precio_texto": None, "precio_fuente": None}


def extract_direccion_texto(jsonld: list, meta: dict) -> dict:
    """
    Texto candidato de dirección (calle/numero) para que
    address_normalizer.parse_calle_numero lo procese, y localidad/barrio
    por separado cuando el JSON-LD los distingue explícitamente.
    """
    street = _jsonld_get(
        jsonld,
        "address.streetAddress",
        "offers.availableAtOrFrom.address.streetAddress",
        "location.address.streetAddress",
    )
    locality = _jsonld_get(
        jsonld,
        "address.addressLocality",
        "location.address.addressLocality",
    )
    region = _jsonld_get(
        jsonld,
        "address.addressRegion",
        "location.address.addressRegion",
    )
    postal = _jsonld_get(
        jsonld,
        "address.postalCode",
        "location.address.postalCode",
    )

    if street or locality:
        # Viene de campos schema.org YA decompuestos (streetAddress,
        # addressLocality por separado) -> tier de mayor confianza que un
        # JSON-LD genérico sin decomponer. Ver jerarquía en record_builder.
        return {
            "direccion_texto": street,
            "localidad_texto": locality,
            "provincia_texto": region,
            "codigo_postal": postal,
            "direccion_fuente": "DIRECCION_ESTRUCTURADA" if street else None,
            "localidad_fuente": "DIRECCION_ESTRUCTURADA" if locality else None,
        }

    og_locality = meta.get("business:contact_data:locality") or meta.get("place:location:locality")
    if og_locality:
        return {
            "direccion_texto": None,
            "localidad_texto": og_locality,
            "provincia_texto": meta.get("business:contact_data:region"),
            "codigo_postal": meta.get("business:contact_data:postal_code"),
            "direccion_fuente": None,
            "localidad_fuente": "META",
        }

    return {
        "direccion_texto": None,
        "localidad_texto": None,
        "provincia_texto": None,
        "codigo_postal": None,
        "direccion_fuente": None,
        "localidad_fuente": None,
    }


def extract_tipo_texto(jsonld: list, titulo: Optional[str]) -> dict:
    """El "tipo" casi nunca viene estructurado; se infiere del título."""
    tipo_schema = _jsonld_get(jsonld, "@type")
    candidato = titulo or tipo_schema
    return {"tipo_texto": candidato, "tipo_fuente": "TEXTO_PUBLICACION" if titulo else "JSON_LD"}


def extract_all(fetch_result) -> dict:
    """Punto de entrada único: recibe un base_scraper.FetchResult."""
    soup = BeautifulSoup(fetch_result.html, "lxml") if fetch_result.html else None
    jsonld = fetch_result.jsonld
    meta = fetch_result.meta

    out = {}
    out.update(extract_titulo(jsonld, meta, soup))
    out.update(extract_descripcion(jsonld, meta))
    out.update(extract_precio_texto(jsonld, meta))
    out.update(extract_direccion_texto(jsonld, meta))
    out.update(extract_tipo_texto(jsonld, out.get("titulo_publicacion")))

    # Texto combinado para regex de ambientes/superficie/amenities
    out["texto_combinado"] = " ".join(
        filter(None, [out.get("titulo_publicacion"), out.get("descripcion_publicacion")])
    ) or None

    return out
