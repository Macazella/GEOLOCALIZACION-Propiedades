"""
Normalización geográfica de direcciones para geocodificación.

Reglas duras (pedidas explícitamente):
- Nunca inventar calle, altura o localidad que no esté en el texto original.
- localidad / partido / provincia son conceptos separados, nunca se
  fusionan ni se infiere uno a partir de otro salvo por los diccionarios
  de sinónimos explícitos de abajo (que son equivalencias de nombre, no
  inferencias geográficas).
- "al 4000" (aproximación de cuadra) NO se convierte en un número exacto.
"""

import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import Optional

# --- Sinónimos de nombre (misma entidad, distinta forma de escribirla) ---

CABA_SYNONYMS = {
    "ciudad autonoma de buenos aires": "Ciudad Autónoma de Buenos Aires",
    "caba": "Ciudad Autónoma de Buenos Aires",
    "capital federal": "Ciudad Autónoma de Buenos Aires",
}

PROVINCIA_BSAS_SYNONYMS = {
    "buenos aires": "Buenos Aires",
    "pcia. buenos aires": "Buenos Aires",
    "pcia buenos aires": "Buenos Aires",
    "provincia de buenos aires": "Buenos Aires",
}

# Localidad -> Partido (NO se infiere geografía nueva: es la relación
# administrativa real, documentada, de los partidos del conurbano sur que
# aparecen en la planilla). Si una localidad no está en este diccionario,
# el partido queda como UNKNOWN y NO se completa con una suposición.
LOCALIDAD_A_PARTIDO = {
    "lanus": "Lanús",
    "lanus oeste": "Lanús",
    "lanus este": "Lanús",
    "remedios de escalada": "Lanús",
    "valentin alsina": "Lanús",
    "monte chingolo": "Lanús",
    "lomas de zamora": "Lomas de Zamora",
    "banfield": "Lomas de Zamora",
    "temperley": "Lomas de Zamora",
    "lavallol": "Lomas de Zamora",
    "turdera": "Lomas de Zamora",
    "avellaneda": "Avellaneda",
    "sarandi": "Avellaneda",
    "gerli": "Avellaneda",
    "wilde": "Avellaneda",
    "quilmes": "Quilmes",
    "bernal": "Quilmes",
    "berazategui": "Berazategui",
}

# Placeholders que aparecen tal cual en la columna "Localidad / Barrio" de
# la planilla cuando nadie completó el dato a mano — NO son una localidad
# real, así que nunca deben usarse como si lo fueran (ej. terminar
# afirmando address_precision=EXACT_ADDRESS con "No identificado" como
# única "localidad" encontrada).
LOCALIDAD_PLACEHOLDERS = {
    "no identificado", "sin identificar", "no especificado",
    "sin especificar", "s/d", "n/a", "-", "no informado",
}

# Correcciones de ortografía/formato de nombres de calle conocidos que
# aparecen en el texto de las publicaciones sin el caracter especial
# correcto (ej. la web sanea el apóstrofo de "O'Higgins" y queda
# "Ohiggins"). Esto NO es inventar un dato: es la misma calle real, solo
# que el sitio de origen la escribió sin el apóstrofo. Solo se aplica en
# match exacto (sin acentos, en minúsculas) — nunca se adivina una calle
# que no esté en este diccionario.
CALLE_CANONICA = {
    "ohiggins": "O'Higgins",
    "o higgins": "O'Higgins",
    "ohigins": "O'Higgins",
}

# Tokens que en realidad son el nombre del sitio/portal/inmobiliaria, no
# parte del nombre de una calle — se arrastran por error cuando el título
# de la página ("... | BuscadorProp") queda pegado al texto de la
# descripción durante el parseo de texto libre. Lista genérica de
# portales grandes; el nombre de la inmobiliaria puntual de cada fila
# (columna "Fuente" de la planilla) se agrega dinámicamente en
# strip_known_brand_prefix().
_BRAND_TOKENS_GENERICOS = [
    "BuscadorProp", "RE/MAX", "REMAX", "RE MAX", "MercadoLibre", "Mercado Libre",
    "Zonaprop", "Argenprop", "Properati",
]


def canonicalize_calle(calle: Optional[str]) -> Optional[str]:
    """Corrige la forma de una calle SOLO si está en CALLE_CANONICA
    (match exacto sin acentos/mayúsculas). Nunca inventa ni adivina."""
    if not calle:
        return calle
    key = _clean_key(calle)
    return CALLE_CANONICA.get(key, calle)


def strip_known_brand_prefix(calle: Optional[str], fuente_sitio: Optional[str] = None) -> Optional[str]:
    """
    Elimina del INICIO de una calle candidata los tokens que en realidad
    son el nombre del sitio/inmobiliaria (arrastrados por el parseo de
    texto libre cuando el título de la página queda pegado a la
    descripción, ej. "...| BuscadorProp Rivadavia 1234" -> calle
    capturada "BuscadorProp Rivadavia" en vez de "Rivadavia").
    `fuente_sitio` es el valor de la columna "Fuente" de la planilla para
    esa fila puntual (ej. "Coviella Propiedades"), para cubrir también
    inmobiliarias chicas sin necesidad de una lista exhaustiva
    hardcodeada.
    """
    if not calle:
        return calle

    candidatos = list(_BRAND_TOKENS_GENERICOS)
    if fuente_sitio and fuente_sitio.strip():
        candidatos.append(fuente_sitio.strip())

    calle_limpia = calle
    cambiado = True
    while cambiado:
        cambiado = False
        for brand in candidatos:
            prefijo = brand.strip()
            if not prefijo:
                continue
            if calle_limpia.lower().startswith(prefijo.lower() + " "):
                calle_limpia = calle_limpia[len(prefijo):].strip()
                cambiado = True

    return calle_limpia or None


# Forma canónica de cada localidad (para mostrar con acentos correctos)
LOCALIDAD_CANONICA = {
    "lanus": "Lanús",
    "lanus oeste": "Lanús Oeste",
    "lanus este": "Lanús Este",
    "remedios de escalada": "Remedios de Escalada",
    "valentin alsina": "Valentín Alsina",
    "monte chingolo": "Monte Chingolo",
    "lomas de zamora": "Lomas de Zamora",
    "banfield": "Banfield",
    "temperley": "Temperley",
    "lavallol": "Lavallol",
    "turdera": "Turdera",
    "avellaneda": "Avellaneda",
    "sarandi": "Sarandí",
    "gerli": "Gerli",
    "wilde": "Wilde",
    "quilmes": "Quilmes",
    "bernal": "Bernal",
    "berazategui": "Berazategui",
}


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def _clean_key(text: str) -> str:
    return _strip_accents(text).lower().strip()


def normalize_provincia(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = _clean_key(raw)
    return PROVINCIA_BSAS_SYNONYMS.get(key, raw.strip())


def normalize_localidad_o_caba(raw: Optional[str]) -> dict:
    """
    Devuelve {"localidad": ..., "partido": ..., "provincia": ...} a partir
    de un texto de localidad/barrio. Si el texto corresponde a CABA, la
    "localidad" pasa a ser el barrio tal cual vino (no se inventa cuál es),
    partido = None (CABA no tiene partidos) y provincia = "Ciudad Autónoma
    de Buenos Aires".
    """
    if not raw or not raw.strip():
        return {"localidad": None, "partido": None, "provincia": None}

    key = _clean_key(raw)

    if key in LOCALIDAD_PLACEHOLDERS:
        # "No identificado" / "Sin especificar" / etc. no son una
        # localidad real: son el placeholder que queda en la planilla
        # cuando nadie completó el dato a mano. Tratarlo como tal
        # (sentinel -> None) es lo que evita, por ejemplo, terminar
        # afirmando EXACT_ADDRESS con esa cadena como única "localidad"
        # conocida.
        return {"localidad": None, "partido": None, "provincia": None}

    if key in CABA_SYNONYMS:
        return {"localidad": None, "partido": None, "provincia": CABA_SYNONYMS[key]}

    # "Almagro (CABA)" -> barrio=Almagro, provincia=CABA
    caba_match = re.match(r"^(.*)\(caba\)$", raw.strip(), flags=re.IGNORECASE)
    if caba_match:
        barrio = caba_match.group(1).strip()
        return {"localidad": barrio, "partido": None, "provincia": "Ciudad Autónoma de Buenos Aires"}

    if key in LOCALIDAD_A_PARTIDO:
        return {
            "localidad": LOCALIDAD_CANONICA.get(key, raw.strip()),
            "partido": LOCALIDAD_A_PARTIDO[key],
            "provincia": "Buenos Aires",
        }

    # Localidad no catalogada: se conserva tal cual, sin inventar partido.
    return {"localidad": raw.strip(), "partido": None, "provincia": None}


# --- Parsing de calle + altura ---

# "Av. Hipólito Yrigoyen 4200" / "Sarandí 206" / "Av. Hipólito Yrigoyen al 4000"
_STREET_NUMBER_RE = re.compile(
    r"^(?P<calle>.+?)\s+(?:(?P<al>al)\s+)?(?P<numero>\d{1,6})\s*$"
)
_UNIT_RE = re.compile(r"\b(?:piso|p\.?)\s*(?P<piso>\d{1,3})\b", re.IGNORECASE)
_DEPTO_RE = re.compile(r"\b(?:depto\.?|dpto\.?|unidad)\s*[\"']?(?P<depto>[a-z0-9]{1,4})[\"']?", re.IGNORECASE)


@dataclass
class AddressParts:
    calle: Optional[str] = None
    numero: Optional[str] = None
    piso: Optional[str] = None
    departamento_unidad: Optional[str] = None
    es_aproximado: bool = False  # True si vino como "al 4000"


def parse_calle_numero(raw_address_line: str) -> AddressParts:
    """
    Extrae calle/número de una línea de dirección tipo "Av. X 1234" o
    "Av. X al 1200". No inventa número si no está presente en el texto.
    """
    if not raw_address_line or not raw_address_line.strip():
        return AddressParts()

    text = raw_address_line.strip()

    piso_match = _UNIT_RE.search(text)
    depto_match = _DEPTO_RE.search(text)

    # quitamos piso/depto del texto para no confundir el parsing de calle+numero
    text_sin_unidad = text
    for m in (piso_match, depto_match):
        if m:
            text_sin_unidad = text_sin_unidad.replace(m.group(0), "")
    text_sin_unidad = re.sub(r"[,]+", " ", text_sin_unidad).strip()

    match = _STREET_NUMBER_RE.match(text_sin_unidad)
    if not match:
        # Sin número reconocible: se guarda como calle "cruda", sin altura.
        return AddressParts(
            calle=text_sin_unidad or None,
            piso=piso_match.group("piso") if piso_match else None,
            departamento_unidad=depto_match.group("depto") if depto_match else None,
        )

    return AddressParts(
        calle=match.group("calle").strip(),
        numero=match.group("numero"),
        piso=piso_match.group("piso") if piso_match else None,
        departamento_unidad=depto_match.group("depto") if depto_match else None,
        es_aproximado=bool(match.group("al")),
    )


# --- Ensamblado final ---

ADDRESS_PRECISION_LEVELS = [
    "EXACT_ADDRESS",
    "BLOCK_APPROXIMATION",
    "STREET_ONLY",
    "LOCALITY_ONLY",
    "UNKNOWN",
]


def build_normalized_address(
    calle: Optional[str],
    numero: Optional[str],
    es_aproximado: bool,
    localidad: Optional[str],
    partido: Optional[str],
    provincia: Optional[str],
) -> dict:
    """
    Devuelve {"address_normalized": str|None, "address_precision": str}.
    NUNCA inventa un componente ausente: si falta la provincia, no se
    asume "Buenos Aires" ni "Argentina" salvo que ya se haya normalizado
    explícitamente antes.
    """
    # dict.fromkeys en vez de set() para no perder el orden localidad -> partido -> provincia
    partes_geo = list(dict.fromkeys(p for p in [localidad, partido, provincia] if p))

    if not calle and not partes_geo:
        return {"address_normalized": None, "address_precision": "UNKNOWN"}

    if not calle:
        return {
            "address_normalized": ", ".join(partes_geo) or None,
            "address_precision": "LOCALITY_ONLY" if partes_geo else "UNKNOWN",
        }

    if not numero:
        direccion = ", ".join(dict.fromkeys([calle] + partes_geo))
        return {"address_normalized": direccion, "address_precision": "STREET_ONLY"}

    calle_completa = f"{calle} {numero}"
    direccion = ", ".join(dict.fromkeys([calle_completa] + partes_geo))

    if not partes_geo:
        # Tenemos calle+número pero NINGÚN dato geográfico (localidad,
        # partido o provincia) para ubicarlos: una calle puede repetirse
        # en decenas de localidades distintas, así que sin ese contexto
        # no alcanza para afirmar EXACT_ADDRESS/BLOCK_APPROXIMATION —
        # corregido tras el piloto v2 (antes se afirmaba EXACT_ADDRESS
        # incluso cuando la única "localidad" disponible era un
        # placeholder tipo "No identificado").
        return {"address_normalized": direccion, "address_precision": "STREET_ONLY"}

    precision = "BLOCK_APPROXIMATION" if es_aproximado else "EXACT_ADDRESS"
    return {"address_normalized": direccion, "address_precision": precision}
