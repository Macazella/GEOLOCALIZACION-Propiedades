"""
Detecta cuándo el scraping "funcionó" (HTTP 200, hubo HTML) pero la
página obtenida es institucional/genérica (ej. la home de la
inmobiliaria) en vez de la ficha real de la propiedad. Evita marcar esos
casos como SUCCESS.

Caso real del piloto: Caramés Propiedades devolvió título "Caramés
Bienes Raíces" y descripción "Inmobiliaria en Lanús y GBA sur...
propiedades en venta y alquiler..." para una URL que claramente es
"casa-en-venta-en-lanus-oeste". La trampa: la descripción institucional
también menciona "venta"/"alquiler" de forma genérica, así que NO alcanza
con buscar esas palabras sueltas — hay que priorizar si el TÍTULO en sí
es el nombre de la empresa, no el de una publicación.
"""

import re
from typing import Optional

# Patrones de título que son el nombre de la empresa, no una publicación
# real (ej. "Caramés Bienes Raíces", "Inmobiliaria Pérez", "XYZ Propiedades").
_TITULO_INSTITUCIONAL_RE = re.compile(
    r"^[\wÀ-ÿ\s]{2,30}\s+(bienes\s*ra[ií]ces|propiedades|inmobiliaria)\s*$"
    r"|^(bienes\s*ra[ií]ces|propiedades|inmobiliaria)\s+[\wÀ-ÿ\s]{2,30}$",
    re.IGNORECASE,
)


def parece_pagina_generica(
    titulo: Optional[str],
    tipo_normalizado: Optional[str],
    tiene_precio: bool,
    tiene_direccion_real: bool,
) -> tuple[bool, str]:
    """
    tiene_direccion_real: True solo si la dirección vino de un scraping
    real (no del fallback a la planilla original) — una dirección de
    planilla no es evidencia de que la página tenga contenido real.

    Devuelve (es_generica, motivo). Señales fuertes de contenido real
    (precio o dirección real extraída) siempre ganan: nunca se marca
    GENERIC_PAGE si alguna de las dos está presente.
    """
    if tiene_precio or tiene_direccion_real:
        return False, ""

    titulo_norm = (titulo or "").strip()

    if titulo_norm and _TITULO_INSTITUCIONAL_RE.match(titulo_norm) and tipo_normalizado == "OTRO":
        return True, f"titulo_parece_nombre_de_empresa='{titulo_norm}'"

    if not titulo_norm and tipo_normalizado == "OTRO":
        return True, "sin_titulo_ni_precio_ni_direccion_real"

    return False, ""
