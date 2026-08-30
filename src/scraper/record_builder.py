"""
Arma el registro enriquecido final de UNA propiedad.

v2 (tras revisión del piloto v1): ya no se confía ciegamente en un único
valor por campo. Para dirección y apto_credito se contrastan DOS fuentes
independientes (dato estructurado del sitio vs. texto libre de
título/descripción) y, si difieren, se preservan ambas explícitamente en
vez de elegir una a ciegas. scrape_status distingue ahora una ficha real
de una página institucional/genérica.
"""

from datetime import datetime
from typing import Callable, Optional

from src.scraper import base_scraper, extractors
from src.scraper.address_text_parser import extract_address_candidate, resolve_candidate_parts
from src.scraper.generic_page_detector import parece_pagina_generica
from src.scraper.type_from_url import infer_tipo_from_url
from src.normalization import address_normalizer as addr
from src.normalization.address_normalizer import strip_known_brand_prefix, canonicalize_calle
from src.normalization import property_normalizer as prop
from src.normalization import conflict_utils
from src.utils.logging_utils import get_logger

logger = get_logger("record_builder")

# Jerarquía de fuentes de dirección ESTRUCTURADA (mayor a menor
# confianza). No se usa para elegir entre múltiples candidatos
# simultáneos (solo hay uno por registro, según qué extractor de dominio
# corrió), sino como documentación/registro de qué tan confiable es.
ADDRESS_SOURCE_PRIORITY = ["REMAX_NG_STATE", "DIRECCION_ESTRUCTURADA", "JSON_LD", "META"]

# Mismo set de claves que produce _build_record_unsafe(), para que un
# registro "esqueleto" (cuando algo revienta antes de llegar a armar el
# dict real) tenga EXACTAMENTE la misma forma que uno normal — así el
# export a CSV/Excel/GeoJSON de las 511 filas nunca se rompe ni pierde
# columnas por una fila con menos claves que las demás.
_CAMPOS_VACIOS = {
    "estado_publicacion": None, "titulo_publicacion": None, "titulo_publicacion_fuente": None,
    "tipo_original_planilla": None, "tipo_propiedad_original": None,
    "tipo_propiedad_normalizado": "OTRO", "tipo_fuente": None,
    "direccion_original_planilla": None, "address_structured": None, "address_text": None,
    "address_conflict": False, "address_conflict_details": None, "address_original": None,
    "address_normalized": None, "address_precision": "UNKNOWN", "address_source": None,
    "calle": None, "numero": None, "piso": None, "departamento_unidad": None,
    "localidad": None, "partido": None, "provincia": None, "codigo_postal": None,
    "precio": None, "moneda": None, "precio_fuente": None, "expensas": None, "expensas_fuente": None,
    "ambientes": None, "dormitorios": None, "banos": None,
    "superficie_total_m2": None, "superficie_total_fuente": None, "superficie_total_confidence": "SIN_SENIAL",
    "superficie_cubierta_m2": None, "superficie_descubierta_m2": None,
    "anio_construccion": None, "antiguedad_anios": None, "antiguedad_fuente": None,
    "cochera": None, "patio": None, "terraza": None, "jardin": None, "balcon": None, "parrilla": None,
    "apto_credito_structured": None, "apto_credito_text": None, "apto_credito_final": None,
    "apto_credito_conflict": False, "apto_credito_conflict_details": None,
    "apto_profesional": None, "orientacion": None, "disposicion": None, "descripcion_publicacion": None,
    "http_status": None, "scrape_method": None, "scrape_status_motivo": None,
    "latitude_sitio": None, "longitude_sitio": None, "coordinates_source": None,
}


def _skeleton_record(planilla_row: dict, error_msg: str) -> dict:
    """
    Registro de emergencia cuando algo revienta de forma inesperada
    ANTES de poder armar el record normal (no debería pasar nunca en el
    camino feliz, pero con 511 URLs reales no se puede asumir que ningún
    sitio va a tener una sorpresa que ningún regex/normalizador
    contempló). Nunca se pierde la fila: queda con scrape_status=ERROR y
    needs_manual_review=True, con todo lo que SÍ se puede tomar de la
    planilla (URL, fuente, comentario personal, ranking) preservado.
    """
    url = planilla_row.get("URL")
    logger.error(f"Excepcion no manejada construyendo el registro de {url}: {error_msg}")
    record = dict(_CAMPOS_VACIOS)
    record.update({
        "url": url,
        "fuente": planilla_row.get("Fuente"),
        "tipo_original_planilla": planilla_row.get("Tipo"),
        "direccion_original_planilla": planilla_row.get("Localidad / Barrio"),
        "comentario_personal": planilla_row.get("Comentario personal"),
        "dato_original_planilla_ranking": planilla_row.get("Ranking"),
        "dato_original_planilla_prioridad_zona": planilla_row.get("Prioridad de zona"),
        "fecha_scraping": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scrape_status": "ERROR",
        "needs_manual_review": True,
        "needs_manual_review_reasons": ["scrape_status=ERROR", "excepcion_no_manejada", str(error_msg)[:200]],
        "_from_cache": False,
    })
    return record


def build_record(
    planilla_row: dict,
    use_cache: bool = True,
    domain_overrides: Optional[Callable] = None,
) -> dict:
    """Wrapper defensivo: ninguna excepción inesperada de _build_record_unsafe
    puede tirar abajo la corrida completa ni hacer perder una fila de las 511."""
    try:
        return _build_record_unsafe(planilla_row, use_cache=use_cache, domain_overrides=domain_overrides)
    except Exception as e:
        return _skeleton_record(planilla_row, str(e))


def _build_record_unsafe(
    planilla_row: dict,
    use_cache: bool = True,
    domain_overrides: Optional[Callable] = None,
) -> dict:
    url = planilla_row["URL"]

    fetch_result = base_scraper.fetch(url, use_cache=use_cache)
    extracted = extractors.extract_all(fetch_result) if fetch_result.html else {}

    overrides = {}
    if domain_overrides and fetch_result.html:
        try:
            overrides = domain_overrides(fetch_result) or {}
        except Exception:
            overrides = {}

    # Overrides de texto crudo: reemplazan lo que trajo el extractor
    # genérico y siguen el mismo camino de normalización de siempre.
    for campo_texto, campo_fuente in [
        ("titulo_publicacion", "titulo_publicacion_fuente"),
        ("descripcion_publicacion", "descripcion_publicacion_fuente"),
        ("tipo_texto", "tipo_fuente"),
        ("direccion_texto", "direccion_fuente"),
        ("localidad_texto", "localidad_fuente"),
    ]:
        if overrides.get(campo_texto):
            extracted[campo_texto] = overrides[campo_texto]
            if overrides.get(campo_fuente):
                extracted[campo_fuente] = overrides[campo_fuente]

    if overrides.get("titulo_publicacion") or overrides.get("descripcion_publicacion"):
        extracted["texto_combinado"] = " ".join(
            filter(None, [extracted.get("titulo_publicacion"), extracted.get("descripcion_publicacion")])
        ) or None

    texto_combinado = extracted.get("texto_combinado")

    # ================= TIPO =================
    tipo_scraped = prop.normalize_tipo(extracted.get("tipo_texto"))
    tipo_planilla = planilla_row.get("Tipo")

    url_tipo, url_tipo_fuente = infer_tipo_from_url(url)
    tipo_conflicto_url = False
    if tipo_scraped["tipo_propiedad_original"] and url_tipo:
        _, tipo_familia_url = (prop.normalize_tipo(url_tipo)["tipo_propiedad_original"], prop.normalize_tipo(url_tipo)["tipo_propiedad_normalizado"])
        if tipo_familia_url != tipo_scraped["tipo_propiedad_normalizado"]:
            tipo_conflicto_url = True

    # ================= PRECIO =================
    if "precio" in overrides:
        precio_info = {"precio": overrides["precio"], "moneda": overrides.get("moneda")}
    else:
        precio_info = prop.normalize_precio(extracted.get("precio_texto") or texto_combinado)

    # ================= AMBIENTES / SUPERFICIE =================
    amb_sup = prop.normalize_ambientes_superficie(texto_combinado)

    superficie_total_m2 = overrides.get("superficie_total_m2", amb_sup["superficie_total_m2"])
    superficie_total_fuente = overrides.get("superficie_total_fuente", amb_sup["superficie_total_fuente"])
    superficie_total_confidence = overrides.get("superficie_total_confidence", amb_sup["superficie_total_confidence"])

    # ================= ANTIGÜEDAD =================
    if "anio_construccion" in overrides or "antiguedad_anios" in overrides:
        antiguedad_info = {
            "anio_construccion": overrides.get("anio_construccion"),
            "antiguedad_anios": overrides.get("antiguedad_anios"),
            "antiguedad_fuente": overrides.get("antiguedad_fuente"),
        }
    else:
        antiguedad_info = prop.normalize_antiguedad(texto_combinado)

    # ================= APTO CRÉDITO (estructurado vs texto) =================
    amenities_texto = prop.normalize_amenities(texto_combinado)
    apto_credito_structured = overrides.get("apto_credito_structured")  # True/False/None (None = sin dato del sitio)
    apto_credito_text = amenities_texto.get("apto_credito")  # True/None

    apto_credito_conflict, apto_credito_conflict_details = conflict_utils.compare_booleans(
        apto_credito_structured, apto_credito_text
    )
    apto_credito_final = apto_credito_structured if apto_credito_structured is not None else apto_credito_text

    # ================= DIRECCIÓN: estructurada vs texto =================
    localidad_texto_planilla = planilla_row.get("Localidad / Barrio")

    # --- Candidato ESTRUCTURADO (del sitio, ng-state / JSON-LD decompuesto) ---
    direccion_estructurada_texto = extracted.get("direccion_texto")
    calle_partes_estructurada = (
        addr.parse_calle_numero(direccion_estructurada_texto) if direccion_estructurada_texto else addr.AddressParts()
    )
    address_structured = None
    if calle_partes_estructurada.calle:
        address_structured = {
            "calle": canonicalize_calle(calle_partes_estructurada.calle),
            "numero": calle_partes_estructurada.numero,
            "fuente": extracted.get("direccion_fuente"),
            "texto_original": direccion_estructurada_texto,
        }

    # --- Candidato de TEXTO (título/descripción), siempre se intenta,
    #     independientemente de si hay uno estructurado, para poder
    #     contrastar. ---
    fuente_sitio_planilla = planilla_row.get("Fuente")

    address_text = None
    candidato_texto = extract_address_candidate(texto_combinado) if texto_combinado else None
    if candidato_texto:
        resuelto = resolve_candidate_parts(candidato_texto)
        # Limpieza (agregada tras piloto v2): el parseo de texto libre a
        # veces arrastra el nombre del sitio/inmobiliaria al principio de
        # la calle (ej. título "...| BuscadorProp" pegado a la
        # descripción "Rivadavia 1234..." -> capturaba "BuscadorProp
        # Rivadavia"). Se limpia ese prefijo y se corrige la ortografía de
        # calles conocidas (ej. "Ohiggins" -> "O'Higgins") solo si están
        # en el diccionario — nunca se inventa una calle nueva.
        calle_limpia = strip_known_brand_prefix(resuelto["calle"], fuente_sitio=fuente_sitio_planilla)
        calle_limpia = canonicalize_calle(calle_limpia)
        address_text = {
            "calle": calle_limpia,
            "numero": resuelto["numero"],
            "localidad": resuelto["localidad"],
            "fuente": resuelto["fuente"],
            "texto_original": resuelto["texto_fuente"],
        }

    # --- Conflicto ---
    address_conflict = False
    address_conflict_details = None
    if address_structured and address_text:
        conflicto_calle, detalle_calle = conflict_utils.compare_streets(
            address_structured["calle"], address_text["calle"]
        )
        conflicto_numero, detalle_numero = conflict_utils.compare_numbers(
            address_structured["numero"], address_text["numero"]
        )
        if conflicto_calle or conflicto_numero:
            address_conflict = True
            address_conflict_details = "; ".join(d for d in [detalle_calle, detalle_numero] if d)

    # --- Localidad/partido/provincia (independiente del conflicto de calle/numero) ---
    localidad_texto_scraped = extracted.get("localidad_texto") or (address_text or {}).get("localidad")
    localidad_fuente_texto = localidad_texto_scraped or localidad_texto_planilla
    localidad_fuente_tag = extracted.get("localidad_fuente") or (
        "TEXTO_PUBLICACION" if (address_text or {}).get("localidad") else None
    ) or ("PLANILLA_ORIGINAL" if localidad_texto_planilla else None)

    geo = addr.normalize_localidad_o_caba(localidad_fuente_texto)
    provincia_final = addr.normalize_provincia(geo["provincia"]) if geo["provincia"] else extracted.get("provincia_texto")

    # --- Resolución de address_final ---
    if address_structured:
        calle_final, numero_final = address_structured["calle"], address_structured["numero"]
        address_source_final = address_structured["fuente"]
        es_aproximado = calle_partes_estructurada.es_aproximado
    elif address_text:
        calle_final, numero_final = address_text["calle"], address_text["numero"]
        address_source_final = address_text["fuente"]
        es_aproximado = False
    else:
        calle_final, numero_final = None, None
        address_source_final = localidad_fuente_tag
        es_aproximado = False

    normalized_addr = addr.build_normalized_address(
        calle=calle_final, numero=numero_final, es_aproximado=es_aproximado,
        localidad=geo["localidad"], partido=geo["partido"], provincia=provincia_final,
    )

    # Si hay conflicto real entre fuentes, la precisión NUNCA puede
    # quedar como EXACT_ADDRESS — el número en disputa no es confiable.
    address_precision_final = normalized_addr["address_precision"]
    if address_conflict and address_precision_final == "EXACT_ADDRESS":
        address_precision_final = "BLOCK_APPROXIMATION"

    # ================= DETECCIÓN DE PÁGINA GENÉRICA =================
    tiene_precio = precio_info["precio"] is not None
    tiene_direccion_real = address_source_final not in (None, "PLANILLA_ORIGINAL")
    es_generica, motivo_generica = parece_pagina_generica(
        titulo=extracted.get("titulo_publicacion"),
        tipo_normalizado=tipo_scraped["tipo_propiedad_normalizado"],
        tiene_precio=tiene_precio,
        tiene_direccion_real=tiene_direccion_real,
    )

    tipo_original_final = tipo_scraped["tipo_propiedad_original"] or tipo_planilla
    tipo_normalizado_final = tipo_scraped["tipo_propiedad_normalizado"]
    tipo_fuente_final = extracted.get("tipo_fuente") if tipo_scraped["tipo_propiedad_original"] else "PLANILLA_ORIGINAL"

    # Fallback fuerte por URL SOLO si la página es genérica y no hay tipo real.
    if es_generica and url_tipo and tipo_normalizado_final == "OTRO":
        tipo_desde_url = prop.normalize_tipo(url_tipo)
        tipo_original_final = tipo_desde_url["tipo_propiedad_original"]
        tipo_normalizado_final = tipo_desde_url["tipo_propiedad_normalizado"]
        tipo_fuente_final = "URL"

    # ================= ESTADO DEL SCRAPING =================
    if fetch_result.scrape_status in ("BLOCKED", "NOT_FOUND", "ERROR"):
        scrape_status = fetch_result.scrape_status
    elif es_generica:
        scrape_status = "GENERIC_PAGE"
    elif not extracted.get("titulo_publicacion") and not tiene_precio and not tiene_direccion_real:
        scrape_status = "PARTIAL"
    elif not tiene_precio and not tiene_direccion_real:
        scrape_status = "PARTIAL"
    else:
        scrape_status = "SUCCESS"

    # ================= NEEDS_MANUAL_REVIEW =================
    razones_revision = []
    if scrape_status in ("BLOCKED", "ERROR", "NOT_FOUND", "GENERIC_PAGE", "PARTIAL"):
        razones_revision.append(f"scrape_status={scrape_status}")
    if address_conflict:
        razones_revision.append("conflicto_direccion")
    if apto_credito_conflict:
        razones_revision.append("conflicto_apto_credito")
    if superficie_total_confidence == "INVALIDA_INCONSISTENTE_CON_AMBIENTES":
        razones_revision.append("superficie_invalida")
    if tipo_conflicto_url:
        razones_revision.append("tipo_inconsistente_con_url")

    record = {
        # --- Identificación ---
        "url": url,
        "fuente": planilla_row.get("Fuente"),
        "titulo_publicacion": extracted.get("titulo_publicacion"),
        "titulo_publicacion_fuente": extracted.get("titulo_publicacion_fuente"),
        "estado_publicacion": None,

        # --- Tipo ---
        "tipo_original_planilla": tipo_planilla,
        "tipo_propiedad_original": tipo_original_final,
        "tipo_propiedad_normalizado": tipo_normalizado_final,
        "tipo_fuente": tipo_fuente_final,

        # --- Ubicación: se preservan las 3 vistas (estructurada / texto / final) ---
        "direccion_original_planilla": localidad_texto_planilla,
        "address_structured": address_structured,
        "address_text": address_text,
        "address_conflict": address_conflict,
        "address_conflict_details": address_conflict_details,
        "address_original": direccion_estructurada_texto or (address_text or {}).get("texto_original") or localidad_fuente_texto,
        "address_normalized": normalized_addr["address_normalized"],
        "address_precision": address_precision_final,
        "address_source": address_source_final,
        "calle": calle_final,
        "numero": numero_final,
        "piso": calle_partes_estructurada.piso,
        "departamento_unidad": calle_partes_estructurada.departamento_unidad,
        "localidad": geo["localidad"],
        "partido": geo["partido"],
        "provincia": provincia_final,
        "codigo_postal": extracted.get("codigo_postal"),

        # --- Precio ---
        "precio": precio_info["precio"],
        "moneda": precio_info["moneda"],
        "precio_fuente": overrides.get("precio_fuente") if "precio" in overrides else extracted.get("precio_fuente"),
        "expensas": overrides.get("expensas"),
        "expensas_fuente": overrides.get("expensas_fuente"),

        # --- Características ---
        "ambientes": overrides.get("ambientes", amb_sup["ambientes"]),
        "dormitorios": overrides.get("dormitorios", amb_sup["dormitorios"]),
        "banos": overrides.get("banos", amb_sup["banos"]),
        "superficie_total_m2": superficie_total_m2,
        "superficie_total_fuente": superficie_total_fuente,
        "superficie_total_confidence": superficie_total_confidence,
        "superficie_cubierta_m2": overrides.get("superficie_cubierta_m2", amb_sup["superficie_cubierta_m2"]),
        "superficie_descubierta_m2": overrides.get("superficie_descubierta_m2", amb_sup["superficie_descubierta_m2"]),
        "anio_construccion": antiguedad_info["anio_construccion"],
        "antiguedad_anios": antiguedad_info["antiguedad_anios"],
        "antiguedad_fuente": antiguedad_info["antiguedad_fuente"],
        "cochera": overrides["cochera"] if "cochera" in overrides else amenities_texto["cochera"],
        "patio": amenities_texto["patio"],
        "terraza": amenities_texto["terraza"],
        "jardin": amenities_texto["jardin"],
        "balcon": amenities_texto["balcon"],
        "parrilla": amenities_texto["parrilla"],
        "apto_credito_structured": apto_credito_structured,
        "apto_credito_text": apto_credito_text,
        "apto_credito_final": apto_credito_final,
        "apto_credito_conflict": apto_credito_conflict,
        "apto_credito_conflict_details": apto_credito_conflict_details,
        "apto_profesional": overrides.get("apto_profesional", amenities_texto["apto_profesional"]),
        "orientacion": None,
        "disposicion": None,
        "descripcion_publicacion": extracted.get("descripcion_publicacion"),

        # --- Comentario personal (se preserva TEXTUAL, nunca se toca) ---
        "comentario_personal": planilla_row.get("Comentario personal"),

        # --- Trazabilidad de planilla ---
        "dato_original_planilla_ranking": planilla_row.get("Ranking"),
        "dato_original_planilla_prioridad_zona": planilla_row.get("Prioridad de zona"),
        "fecha_scraping": datetime.now().astimezone().isoformat(timespec="seconds"),

        # --- Técnicos ---
        "scrape_status": scrape_status,
        "scrape_status_motivo": motivo_generica or None,
        "http_status": fetch_result.http_status,
        "scrape_method": fetch_result.scrape_method,
        "needs_manual_review": bool(razones_revision),
        "needs_manual_review_reasons": razones_revision,
        "_from_cache": fetch_result.from_cache,

        # Coordenadas ya calculadas por el sitio de origen (ej. RE/MAX).
        # SIEMPRE presentes (con None si no aplica) para que todos los
        # registros tengan el mismo set de columnas — antes se agregaban
        # solo condicionalmente, lo que rompía el export a CSV/Excel en
        # cuanto una fila sin estas claves se procesaba antes que una con
        # ellas (o viceversa).
        "latitude_sitio": overrides.get("latitude_fuente_sitio"),
        "longitude_sitio": overrides.get("longitude_fuente_sitio"),
        "coordinates_source": overrides.get("coordinates_source"),
    }

    return record
