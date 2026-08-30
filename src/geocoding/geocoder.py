"""
Geocodificación con Nominatim (OpenStreetMap), en 4 niveles decrecientes
de precisión. Nunca acepta silenciosamente una coordenada de otra
provincia (ver validators.py). Usa cache en disco para no repetir
consultas sobre la misma dirección normalizada.
"""

import time
from typing import Optional

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderServiceError, GeocoderTimedOut

from src.utils.logging_utils import get_logger
from src.utils.cache import DiskCache
from src.geocoding import validators

logger = get_logger("geocoder")
_cache = DiskCache("geocoding")

_geolocator = Nominatim(user_agent="geolocalizacion_propiedades_maga_v1")
_geocode = RateLimiter(_geolocator.geocode, min_delay_seconds=1.2, max_retries=2, error_wait_seconds=5.0)

GEOCODE_STATUSES = [
    "EXACT", "APPROXIMATE", "LOCALITY_ONLY", "NOT_FOUND", "ERROR",
    "SITE_PROVIDED", "SITE_PROVIDED_CONFLICTO",
]


def _build_queries(record: dict) -> list[tuple[str, str]]:
    """
    Devuelve [(nivel, query_string), ...] en orden de preferencia,
    usando SOLO los componentes que realmente están presentes en el
    registro (nunca se inventa un componente ausente).
    """
    calle = record.get("calle")
    numero = record.get("numero")
    localidad = record.get("localidad")
    partido = record.get("partido")
    provincia = record.get("provincia")

    queries = []

    if calle and numero and localidad and provincia:
        queries.append(("NIVEL_1_CALLE_LOCALIDAD", f"{calle} {numero}, {localidad}, {provincia}, Argentina"))
    if calle and numero and partido and provincia:
        queries.append(("NIVEL_2_CALLE_PARTIDO", f"{calle} {numero}, {partido}, {provincia}, Argentina"))
    if calle and localidad and provincia:
        queries.append(("NIVEL_3_CALLE_SIN_NUMERO", f"{calle}, {localidad}, {provincia}, Argentina"))
    if localidad and provincia:
        queries.append(("NIVEL_4_LOCALIDAD", f"{localidad}, {provincia}, Argentina"))
    elif provincia:
        queries.append(("NIVEL_4_LOCALIDAD", f"{provincia}, Argentina"))

    return queries


def geocode_record(record: dict, use_cache: bool = True) -> dict:
    """
    Agrega al record: latitude, longitude, geocode_status,
    geocode_provider, geocode_query, geocode_level, geocode_confidence,
    geocode_display_name.
    """
    base_result = {
        "latitude": None,
        "longitude": None,
        "geocode_status": "NOT_FOUND",
        "geocode_provider": "Nominatim",
        "geocode_query": None,
        "geocode_level": None,
        "geocode_confidence": None,
        "geocode_display_name": None,
    }

    # Si el sitio de origen (ej. RE/MAX) ya trae coordenadas propias, las
    # usamos directo (nos ahorra una consulta a Nominatim), PERO no se
    # afirma "EXACT" solo porque el sitio las haya devuelto: se marca
    # "SITE_PROVIDED" (precisión distinta a la geocodificada por
    # dirección) y se contrasta contra el estado de la dirección — si la
    # dirección tiene un conflicto sin resolver, el registro entero ya
    # está marcado needs_manual_review, y las coordenadas del sitio
    # quedan igual pero con esa salvedad visible en geocode_status.
    if record.get("latitude_sitio") is not None and record.get("longitude_sitio") is not None:
        lat, lon = record["latitude_sitio"], record["longitude_sitio"]
        is_valid, motivo = validators.validate_coordinates(
            lat=lat, lon=lon, provincia_esperada=record.get("provincia"), raw_address={}
        )
        if is_valid:
            estado = "SITE_PROVIDED_CONFLICTO" if record.get("address_conflict") else "SITE_PROVIDED"
            return {
                "latitude": lat,
                "longitude": lon,
                "geocode_status": estado,
                "geocode_provider": record.get("coordinates_source", "sitio_origen"),
                "geocode_query": None,
                "geocode_level": "COORDENADAS_DEL_SITIO",
                "geocode_confidence": estado,
                "geocode_display_name": None,
            }
        logger.warning(f"Coordenadas del sitio descartadas por validacion ({motivo}) para {record.get('url')}")

    if record.get("address_precision") == "UNKNOWN":
        return base_result  # nada geocodificable, ni intentamos

    queries = _build_queries(record)
    if not queries:
        return base_result

    for nivel, query in queries:
        cache_key = f"{nivel}::{query}"
        cached = _cache.get(cache_key) if use_cache else None
        if cached is not None:
            location_data = cached
        else:
            try:
                location = _geocode(query, country_codes="ar", exactly_one=True, addressdetails=True)
                location_data = (
                    {
                        "lat": location.latitude,
                        "lon": location.longitude,
                        "display_name": location.address,
                        "raw_address": location.raw.get("address", {}),
                    }
                    if location
                    else None
                )
                if use_cache:
                    _cache.set(cache_key, location_data)
            except (GeocoderTimedOut, GeocoderServiceError) as e:
                logger.warning(f"Error geocodificando '{query}': {e}")
                location_data = None

        if location_data is None:
            continue

        # Validación geográfica: nunca aceptar silenciosamente coordenadas
        # fuera de la provincia esperada / fuera de Argentina.
        is_valid, motivo = validators.validate_coordinates(
            lat=location_data["lat"],
            lon=location_data["lon"],
            provincia_esperada=record.get("provincia"),
            raw_address=location_data.get("raw_address", {}),
        )
        if not is_valid:
            logger.warning(f"Geocode descartado por validacion ({motivo}): {query} -> {location_data}")
            continue

        confidence = {
            "NIVEL_1_CALLE_LOCALIDAD": "EXACT",
            "NIVEL_2_CALLE_PARTIDO": "EXACT",
            "NIVEL_3_CALLE_SIN_NUMERO": "APPROXIMATE",
            "NIVEL_4_LOCALIDAD": "LOCALITY_ONLY",
        }[nivel]

        return {
            "latitude": location_data["lat"],
            "longitude": location_data["lon"],
            "geocode_status": confidence,
            "geocode_provider": "Nominatim",
            "geocode_query": query,
            "geocode_level": nivel,
            "geocode_confidence": confidence,
            "geocode_display_name": location_data["display_name"],
        }

    return base_result


def apply_geocode_review_reasons(record: dict) -> None:
    """
    Mutación in-place: si el geocode terminó en NOT_FOUND o ERROR, agrega
    el motivo correspondiente a needs_manual_review_reasons y marca
    needs_manual_review=True. Se llama DESPUÉS de mergear el resultado de
    geocode_record() en el record (el needs_manual_review calculado en
    record_builder.build_record() es previo a la geocodificación, así que
    no puede conocer todavía el resultado del geocoder).
    """
    estado = record.get("geocode_status")
    if estado not in ("NOT_FOUND", "ERROR"):
        return

    motivo = "geocode_not_found" if estado == "NOT_FOUND" else "geocode_error"
    razones = record.get("needs_manual_review_reasons") or []
    if motivo not in razones:
        razones.append(motivo)
    record["needs_manual_review_reasons"] = razones
    record["needs_manual_review"] = True
