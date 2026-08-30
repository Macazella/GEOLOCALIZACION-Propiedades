"""
Extrae una dirección candidata desde texto libre (título/descripción),
como respaldo cuando no hay dato estructurado o para CONTRASTAR contra el
dato estructurado (no para reemplazarlo a ciegas).

Reconoce patrones como:
  "Dirección: Av. 9 de Julio 1829 Lanús Este"
  "Belgrano 1234 entre San Martín y Rivadavia. Quilmes"
  "Rivadavia 4321, entre Mitre y Sarmiento"

Siempre conserva el texto original de donde salió (candidate.texto_fuente).
"""

import re
from dataclasses import dataclass
from typing import Optional

from src.normalization.address_normalizer import (
    parse_calle_numero, normalize_localidad_o_caba, AddressParts,
    LOCALIDAD_A_PARTIDO, CABA_SYNONYMS, _clean_key,
)

# Ordenadas de más larga a más corta para que "lomas de zamora" se
# intente antes que, por ejemplo, un prefijo parcial más corto.
_LOCALIDADES_CONOCIDAS = sorted(
    set(LOCALIDAD_A_PARTIDO.keys()) | set(CABA_SYNONYMS.keys()),
    key=len, reverse=True,
)


@dataclass
class AddressTextCandidate:
    calle: Optional[str] = None
    numero: Optional[str] = None
    localidad: Optional[str] = None
    texto_fuente: Optional[str] = None
    fuente: Optional[str] = None  # TEXTO_ETIQUETADO_DIRECCION o TEXTO_PUBLICACION


# 1) Con etiqueta explícita: "Dirección: <calle> <numero> [localidad]"
_ETIQUETADA_RE = re.compile(
    r"direcci[oó]n\s*:?\s*(?P<calle>[A-Za-zÀ-ÿ0-9°\.\s]+?)\s+(?P<numero>\d{2,6})\b(?P<resto>[^\n\.]{0,60})?",
    re.IGNORECASE,
)

# 2) "<calle> <numero> entre X y Y[. Localidad]" — patrón muy usado en
#    descripciones de propiedades (referencia de "entre calles"). Usamos
#    una clase acotada en vez de ".+?" perezoso: con un grupo final
#    opcional, ".+?" perezoso nunca llega a intentar capturarlo (prefiere
#    matchear cero veces el grupo opcional), así que había que forzarlo a
#    consumir hasta el próximo punto.
_ENTRE_CALLES_RE = re.compile(
    r"(?P<calle>[A-Za-zÀ-ÿ0-9°\.\s]{3,40}?)\s+(?P<numero>\d{2,6})\s+entre\s+[^.\n]{3,60}"
    r"(?:\.\s*(?P<localidad>[A-Za-zÀ-ÿ\s]{2,30}))?",
    re.IGNORECASE,
)

# 3) "<calle> <numero>, entre X y Y" (con coma en vez de "entre" directo)
_COMA_ENTRE_RE = re.compile(
    r"(?P<calle>[A-Za-zÀ-ÿ0-9°\.\s]{3,40}?)\s+(?P<numero>\d{2,6}),\s*entre\s+",
    re.IGNORECASE,
)


def _limpiar_calle(calle: str) -> str:
    return re.sub(r"\s+", " ", calle).strip(" ,.")


def _validar_localidad_conocida(localidad_raw: Optional[str]) -> Optional[str]:
    """
    Antes se aceptaba el candidato de localidad si empezaba con mayúscula
    (heurística anti-basura), pero eso descarta localidades reales
    escritas en minúscula en la publicación (ej. "...famatina. lomas de
    zamora cocina..."). Y validar el string COMPLETO contra el
    diccionario tampoco alcanza, porque la regex de origen suele arrastrar
    palabras de más después de la localidad real (ej. "lomas de zamora
    cocina comedor..." en vez de "lomas de zamora" solo).

    Por eso acá se busca, DENTRO del fragmento candidato, el nombre de
    alguna localidad ya conocida por el diccionario (match de palabra
    completa, sin acentos/mayúsculas, probando las más largas primero
    para no matchear "lanus" dentro de "lanus este"). Nunca se inventa
    una localidad fuera de ese diccionario.
    """
    if not localidad_raw:
        return None
    key_candidato = _clean_key(localidad_raw)
    for loc_key in _LOCALIDADES_CONOCIDAS:
        if re.search(rf"\b{re.escape(loc_key)}\b", key_candidato):
            return loc_key
    return None


def extract_address_candidate(texto: Optional[str]) -> Optional[AddressTextCandidate]:
    if not texto:
        return None

    m = _ETIQUETADA_RE.search(texto)
    if m:
        calle = _limpiar_calle(m.group("calle"))
        localidad = None
        resto = m.group("resto") or ""
        # Si después del número queda una palabra con mayúscula que no es
        # "entre X y Y", la tomamos como localidad candidata (conservadora).
        resto_limpio = resto.strip(" ,.")
        if resto_limpio and "entre" not in resto_limpio.lower() and len(resto_limpio) < 40:
            localidad = resto_limpio
        return AddressTextCandidate(
            calle=calle, numero=m.group("numero"), localidad=localidad,
            texto_fuente=m.group(0).strip(), fuente="TEXTO_ETIQUETADO_DIRECCION",
        )

    m = _COMA_ENTRE_RE.search(texto)
    if m:
        return AddressTextCandidate(
            calle=_limpiar_calle(m.group("calle")), numero=m.group("numero"),
            texto_fuente=m.group(0).strip(), fuente="TEXTO_PUBLICACION",
        )

    m = _ENTRE_CALLES_RE.search(texto)
    if m:
        localidad = _validar_localidad_conocida(m.group("localidad"))
        return AddressTextCandidate(
            calle=_limpiar_calle(m.group("calle")), numero=m.group("numero"),
            localidad=localidad,
            texto_fuente=m.group(0).strip(), fuente="TEXTO_PUBLICACION",
        )

    return None


def resolve_candidate_parts(candidate: AddressTextCandidate) -> dict:
    """Normaliza el candidato a calle/numero/localidad/partido/provincia,
    reutilizando el mismo diccionario de sinónimos que el resto del pipeline."""
    geo = normalize_localidad_o_caba(candidate.localidad) if candidate.localidad else {
        "localidad": None, "partido": None, "provincia": None,
    }
    return {
        "calle": candidate.calle,
        "numero": candidate.numero,
        "localidad": geo["localidad"],
        "partido": geo["partido"],
        "provincia": geo["provincia"],
        "fuente": candidate.fuente,
        "texto_fuente": candidate.texto_fuente,
    }
