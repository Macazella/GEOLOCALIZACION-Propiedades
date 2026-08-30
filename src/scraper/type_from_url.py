"""
Infiere el tipo de propiedad a partir del slug de la URL. Se usa SOLO
como fallback de última instancia cuando la página no aportó un tipo
confiable (ej. página institucional/genérica), nunca como fuente
principal.
"""

import re
from urllib.parse import urlparse

_TOKEN_TO_TIPO = {
    "casa": "Casa",
    "duplex": "Duplex",
    "dplex": "Duplex",  # URLs a veces pierden acentos/vocales al slugificar
    "ph": "PH",
    "departamento": "Departamento",
    "depto": "Departamento",
    "loft": "Loft",
    "monoambiente": "Departamento",
    "terreno": "Terreno",
    "lote": "Terreno",
    "local": "Local Comercial",
    "oficina": "Oficina",
}


def infer_tipo_from_url(url: str) -> tuple[str, str] | tuple[None, None]:
    slug = urlparse(url).path.lower()
    tokens = re.split(r"[-/_]", slug)
    for token in tokens:
        if token in _TOKEN_TO_TIPO:
            return _TOKEN_TO_TIPO[token], "URL"
    return None, None
