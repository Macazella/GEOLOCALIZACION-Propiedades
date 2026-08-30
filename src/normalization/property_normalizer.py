"""
Normalización de atributos de la propiedad (tipo, precio, ambientes,
superficies, antigüedad, amenities) a partir de texto libre / datos
estructurados ya extraídos.

Regla dura: si un dato no está presente, se guarda None (NULL), nunca 0.
Regla dura #2 (agregada tras el piloto v1): un número aislado con "m2"
al lado NO es superficie total — se exige una señal explícita
("total"/"totales"/"cubierta"/"descubierta") cerca del número. Si no hay
señal explícita, se deja NULL en vez de adivinar.
"""

import re
import unicodedata
from datetime import date
from typing import Optional

# Tipo original -> (tipo conservado, familia)
TIPO_FAMILIA = {
    "casa": ("Casa", "CASA"),
    "duplex": ("Duplex", "CASA"),
    "dúplex": ("Duplex", "CASA"),
    "ph": ("PH", "PH"),
    "departamento": ("Departamento", "DEPARTAMENTO"),
    "depto": ("Departamento", "DEPARTAMENTO"),
    "loft": ("Loft", "DEPARTAMENTO"),
    "monoambiente": ("Departamento", "DEPARTAMENTO"),
    "terreno": ("Terreno", "OTRO"),
    "lote": ("Terreno", "OTRO"),
    "local": ("Local Comercial", "OTRO"),
    "oficina": ("Oficina", "OTRO"),
    "galpon": ("Galpón", "OTRO"),
    "galpón": ("Galpón", "OTRO"),
}


def _clean(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower().strip()


def normalize_tipo(texto_original: Optional[str]) -> dict:
    """
    texto_original: título/descripción/tipo crudo de la publicación.
    Devuelve tipo_propiedad_original (tal como se detectó en el texto) y
    tipo_propiedad_normalizado (familia: CASA/PH/DEPARTAMENTO/OTRO).
    """
    if not texto_original:
        return {"tipo_propiedad_original": None, "tipo_propiedad_normalizado": "OTRO"}

    key = _clean(texto_original)
    for token, (conservado, familia) in TIPO_FAMILIA.items():
        if re.search(rf"\b{re.escape(token)}\b", key):
            return {"tipo_propiedad_original": conservado, "tipo_propiedad_normalizado": familia}

    return {"tipo_propiedad_original": texto_original.strip(), "tipo_propiedad_normalizado": "OTRO"}


_PRICE_RE = re.compile(
    r"(?P<moneda>USD|US\$|U\$S|\$)\s*([\d.]{3,12})", re.IGNORECASE
)


def normalize_precio(texto: Optional[str]) -> dict:
    """Extrae precio + moneda de un texto libre (título, JSON-LD price, etc.)."""
    if not texto:
        return {"precio": None, "moneda": None}

    match = _PRICE_RE.search(str(texto))
    if not match:
        return {"precio": None, "moneda": None}

    moneda_raw = match.group("moneda").upper()
    moneda = "USD" if moneda_raw in ("USD", "US$", "U$S") else "ARS"

    numero_raw = match.group(2)
    # Formato AR: "150.000" = 150000 (punto como separador de miles)
    numero_limpio = numero_raw.replace(".", "")
    try:
        precio = int(numero_limpio)
    except ValueError:
        return {"precio": None, "moneda": moneda}

    return {"precio": precio, "moneda": moneda}


_AMBIENTES_RE = re.compile(r"(\d{1,2})\s*amb", re.IGNORECASE)
_DORM_RE = re.compile(r"(\d{1,2})\s*dorm", re.IGNORECASE)
_BANOS_RE = re.compile(r"(\d{1,2})\s*ba[nñ]o", re.IGNORECASE)


def _to_number(raw: str) -> Optional[float]:
    try:
        return float(raw.replace(",", "."))
    except (ValueError, AttributeError):
        return None


_NUMERO_M2_RE = re.compile(r"(\d{1,4}(?:[.,]\d{1,2})?)\s*m[²2]?\b", re.IGNORECASE)


def _find_qualified_surface(texto: str, qualifier: str, exclude_prefixes: tuple = ()) -> Optional[float]:
    """
    Busca un número de m2 asociado a una palabra calificadora explícita
    (ej. "total", "cubiert"). exclude_prefixes evita falsos positivos como
    "descubierta"/"semicubierta" cuando el calificador es "cubiert".

    Orden de búsqueda (corregido tras piloto v2): primero DESPUÉS del
    calificador ("cubierta 67 m2", el caso más común), y solo si ahí no
    hay nada, ANTES del calificador ("67 m2 cubiertos") tomando el número
    más CERCANO (última coincidencia de la ventana), nunca el primero que
    aparezca en una ventana que mira para ambos lados a la vez — eso fue
    lo que causaba que "total 139 m2, cubierta 67 m2" le asignara 139 (el
    número de "total", que quedaba dentro de la ventana "antes") a
    "cubierta" en vez de 67.
    """
    for m in re.finditer(re.escape(qualifier), texto, re.IGNORECASE):
        start = m.start()
        prefijo_excluido = False
        for pref in exclude_prefixes:
            ini = max(0, start - len(pref))
            if texto[ini:start].lower() == pref.lower():
                prefijo_excluido = True
                break
        if prefijo_excluido:
            continue

        ventana_despues = texto[m.end(): m.end() + 25]
        num_match = _NUMERO_M2_RE.search(ventana_despues)
        if not num_match:
            ventana_antes = texto[max(0, start - 25): start]
            matches_antes = list(_NUMERO_M2_RE.finditer(ventana_antes))
            num_match = matches_antes[-1] if matches_antes else None

        if num_match:
            valor = _to_number(num_match.group(1))
            if valor is not None:
                return valor
    return None


_SIN_DATO = {"m2": None, "fuente": None, "confidence": "SIN_SENIAL"}

# Tolerancia (m2) para los chequeos de consistencia cruzada entre
# total/cubierta/descubierta: hay balcones, terrazas u otros espacios que
# a veces no se declaran por separado y desbalancean la suma en unos
# pocos m2 sin que eso implique un dato falso.
_TOLERANCIA_CONSISTENCIA_M2 = 5
INVALIDA_INCONSISTENTE_CON_AMBIENTES = "INVALIDA_INCONSISTENTE_CON_AMBIENTES"
INVALIDA_MAYOR_QUE_TOTAL = "INVALIDA_MAYOR_QUE_TOTAL"


def normalize_ambientes_superficie(texto: Optional[str]) -> dict:
    """
    superficie_total_m2 SOLO se completa si hay una señal explícita de
    "total" cerca del número (nunca un "m2" aislado, p. ej. de un patio o
    balcón mencionado en la descripción). Si no hay señal, queda NULL con
    superficie_total_confidence="SIN_SENIAL". Lo mismo aplica, con su
    propia fuente/confidence, a cubierta y descubierta.

    Sanity checks (agregados tras revisión del piloto v2):
    - Cada componente (total/cubierta/descubierta) se invalida SI SOLO si
      es implausible para la cantidad de ambientes informada (ej. "1 m2"
      para una vivienda de 3 ambientes) — no solo el total, como en la
      primera versión.
    - Consistencia cruzada: cubierta y descubierta no pueden superar el
      total (con tolerancia), y si ambas están presentes su suma debe
      aproximarse al total.
    """
    if not texto:
        return {
            "ambientes": None, "dormitorios": None, "banos": None,
            "superficie_total_m2": None, "superficie_total_fuente": None,
            "superficie_total_confidence": "SIN_SENIAL",
            "superficie_cubierta_m2": None, "superficie_cubierta_fuente": None,
            "superficie_cubierta_confidence": "SIN_SENIAL",
            "superficie_descubierta_m2": None, "superficie_descubierta_fuente": None,
            "superficie_descubierta_confidence": "SIN_SENIAL",
        }

    amb = _AMBIENTES_RE.search(texto)
    dorm = _DORM_RE.search(texto)
    banos = _BANOS_RE.search(texto)

    total = _find_qualified_surface(texto, "total")
    cubierta = _find_qualified_surface(texto, "cubiert", exclude_prefixes=("des", "semi"))
    # "descubierta" casi no se usa en publicaciones reales; "libre" es el
    # sinónimo más común ("cubierta 67 m2, libre 72 m2").
    descubierta = _find_qualified_surface(texto, "descubiert")
    if descubierta is None:
        descubierta = _find_qualified_surface(texto, "libre")

    fuente_total = "TEXTO_PUBLICACION" if total is not None else None
    conf_total = "TEXTO_CON_SENIAL_EXPLICITA" if total is not None else "SIN_SENIAL"
    fuente_cubierta = "TEXTO_PUBLICACION" if cubierta is not None else None
    conf_cubierta = "TEXTO_CON_SENIAL_EXPLICITA" if cubierta is not None else "SIN_SENIAL"
    fuente_descubierta = "TEXTO_PUBLICACION" if descubierta is not None else None
    conf_descubierta = "TEXTO_CON_SENIAL_EXPLICITA" if descubierta is not None else "SIN_SENIAL"

    ambientes_val = int(amb.group(1)) if amb else None

    # --- Sanity check #1: valor implausible para la cantidad de ambientes ---
    # (ej. 1 m2 totales/cubiertos para una vivienda de 3 ambientes). Se
    # aplica a total y cubierta (siempre deberían ser del orden de los
    # ambientes). Se aplica a descubierta SOLO si total y cubierta ya
    # fueron invalidados por el mismo motivo (evita dejar un tercer
    # número "sano" sostenido por el mismo dato erróneo, como en el caso
    # "total 1 m2, cubierta 1 m2, libre 1 m2").
    if ambientes_val:
        minimo_razonable = ambientes_val * 10  # piso muy laxo a propósito, para no descartar casos válidos chicos
        if total is not None and total < minimo_razonable:
            total, fuente_total, conf_total = None, None, INVALIDA_INCONSISTENTE_CON_AMBIENTES
        if cubierta is not None and cubierta < minimo_razonable:
            cubierta, fuente_cubierta, conf_cubierta = None, None, INVALIDA_INCONSISTENTE_CON_AMBIENTES
        if (
            descubierta is not None
            and descubierta < minimo_razonable
            and conf_total == INVALIDA_INCONSISTENTE_CON_AMBIENTES
            and conf_cubierta == INVALIDA_INCONSISTENTE_CON_AMBIENTES
        ):
            descubierta, fuente_descubierta, conf_descubierta = None, None, INVALIDA_INCONSISTENTE_CON_AMBIENTES

    # --- Sanity check #2: consistencia cruzada contra el total ---
    if total is not None:
        if cubierta is not None and cubierta > total + _TOLERANCIA_CONSISTENCIA_M2:
            cubierta, fuente_cubierta, conf_cubierta = None, None, INVALIDA_MAYOR_QUE_TOTAL
        if descubierta is not None and descubierta > total + _TOLERANCIA_CONSISTENCIA_M2:
            descubierta, fuente_descubierta, conf_descubierta = None, None, INVALIDA_MAYOR_QUE_TOTAL
        if cubierta is not None and descubierta is not None:
            suma = cubierta + descubierta
            if abs(suma - total) > _TOLERANCIA_CONSISTENCIA_M2:
                # No se invalida agresivamente (puede haber terraza/balcón
                # no sumado en el texto): se preserva el dato pero se dejs
                # explícita la inconsistencia en el confidence del total.
                if conf_total == "TEXTO_CON_SENIAL_EXPLICITA":
                    conf_total = "TEXTO_CON_SENIAL_EXPLICITA_SUMA_INCONSISTENTE"

    return {
        "ambientes": ambientes_val,
        "dormitorios": int(dorm.group(1)) if dorm else None,
        "banos": int(banos.group(1)) if banos else None,
        "superficie_total_m2": total,
        "superficie_total_fuente": fuente_total,
        "superficie_total_confidence": conf_total,
        "superficie_cubierta_m2": cubierta,
        "superficie_cubierta_fuente": fuente_cubierta,
        "superficie_cubierta_confidence": conf_cubierta,
        "superficie_descubierta_m2": descubierta,
        "superficie_descubierta_fuente": fuente_descubierta,
        "superficie_descubierta_confidence": conf_descubierta,
    }


# --- Antigüedad: año de construcción vs. antigüedad en años son cosas
# distintas y NO deben mezclarse en un mismo campo. ---

_ANIO_CONSTRUCCION_RE = re.compile(
    r"(?:a[nñ]o\s*de\s*construcci[oó]n|construid[ao]\s*en|edificad[ao]\s*en)\D{0,10}?((?:19|20)\d{2})",
    re.IGNORECASE,
)
_ANTIGUEDAD_ANIOS_RE = re.compile(
    r"(\d{1,3})\s*a[nñ]os?\s*de\s*antig[uü]edad|antig[uü]edad\D{0,15}?(\d{1,3})\s*a[nñ]os?",
    re.IGNORECASE,
)
_A_ESTRENAR_RE = re.compile(r"\ba\s*estrenar\b", re.IGNORECASE)


def normalize_antiguedad(texto: Optional[str], anio_actual: Optional[int] = None) -> dict:
    """
    Devuelve anio_construccion (ej. 2022) y antiguedad_anios (ej. 4) como
    campos separados, cada uno con su propia fuente. Nunca se guarda un
    año suelto (1950, 2022) dentro de un campo llamado "antigüedad".
    """
    anio_actual = anio_actual or date.today().year

    if not texto:
        return {"anio_construccion": None, "antiguedad_anios": None, "antiguedad_fuente": None}

    if _A_ESTRENAR_RE.search(texto):
        return {"anio_construccion": None, "antiguedad_anios": 0, "antiguedad_fuente": "TEXTO_PUBLICACION"}

    m_anio = _ANIO_CONSTRUCCION_RE.search(texto)
    if m_anio:
        anio = int(m_anio.group(1))
        return {
            "anio_construccion": anio,
            "antiguedad_anios": max(0, anio_actual - anio),
            "antiguedad_fuente": "TEXTO_PUBLICACION",
        }

    m_antig = _ANTIGUEDAD_ANIOS_RE.search(texto)
    if m_antig:
        anios = int(m_antig.group(1) or m_antig.group(2))
        return {"anio_construccion": None, "antiguedad_anios": anios, "antiguedad_fuente": "TEXTO_PUBLICACION"}

    return {"anio_construccion": None, "antiguedad_anios": None, "antiguedad_fuente": None}


AMENITY_KEYWORDS = {
    "cochera": ["cochera", "garage", "garaje"],
    "patio": ["patio"],
    "terraza": ["terraza"],
    "jardin": ["jardin", "jardín"],
    "balcon": ["balcon", "balcón"],
    "parrilla": ["parrilla", "quincho"],
    "apto_credito": ["apto credito", "apto crédito", "apto para credito"],
    "apto_profesional": ["apto profesional"],
}

# apto_credito es el único amenity que puede aparecer NEGADO en el texto
# ("NO ES APTO CREDITO BANCARIO"). Antes solo se buscaba la afirmación
# como substring, así que "no apto credito" también matcheaba "apto
# credito" y se guardaba True — al revés de lo que decía el texto. Estas
# negaciones se evalúan SIEMPRE antes que la afirmación. Trabaja sobre
# `key`, que ya pasó por _clean() (sin acentos, en minúsculas).
_APTO_CREDITO_NEGATIVO_RE = re.compile(
    r"\bno\s+(?:es\s+)?apto\s+(?:a\s+|para\s+)?credito\b"
    r"|\bno\s+califica\s+para\s+credito\b"
)


def normalize_amenities(texto: Optional[str]) -> dict:
    """
    Devuelve True/None por amenity (nunca False por omisión: "no
    mencionado" no es lo mismo que "confirmado que no tiene"). La única
    excepción es apto_credito, donde una negación explícita en el texto
    SÍ produce False (es un dato afirmativo, no una ausencia de dato).
    """
    if not texto:
        return {k: None for k in AMENITY_KEYWORDS}

    key = _clean(texto)
    result = {}
    for amenity, keywords in AMENITY_KEYWORDS.items():
        if amenity == "apto_credito" and _APTO_CREDITO_NEGATIVO_RE.search(key):
            result[amenity] = False
            continue
        found = any(_clean(kw) in key for kw in keywords)
        result[amenity] = True if found else None
    return result
