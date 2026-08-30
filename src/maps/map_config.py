"""Configuración central de colores/íconos del mapa. Un solo lugar para
tocar la estética — nada de colores sueltos en map_builder.py."""

# Color por familia de tipo de propiedad
COLOR_POR_TIPO = {
    "CASA": "green",
    "PH": "orange",
    "DEPARTAMENTO": "blue",
    "OTRO": "gray",
}

ICONO_POR_TIPO = {
    "CASA": "home",
    "PH": "building",
    "DEPARTAMENTO": "building",
    "OTRO": "question",
}

# Estilo de marcador según precisión geográfica — un marcador aproximado
# NUNCA debe verse igual que uno exacto.
PRECISION_STYLE = {
    "EXACT_ADDRESS": {"icon_prefix": "fa", "opacity": 1.0, "radius_m": None, "label": "Dirección exacta"},
    "BLOCK_APPROXIMATION": {"icon_prefix": "fa", "opacity": 0.75, "radius_m": 150, "label": "Aproximado (altura de cuadra)"},
    "STREET_ONLY": {"icon_prefix": "fa", "opacity": 0.6, "radius_m": 300, "label": "Solo calle, sin altura"},
    "LOCALITY_ONLY": {"icon_prefix": "fa", "opacity": 0.4, "radius_m": 800, "label": "Solo localidad/barrio"},
}

ZONA_GRUPOS = {
    "Lanús": "Lanús",
    "Lomas de Zamora": "Lomas de Zamora",
    "Temperley": "Lomas de Zamora",
    "Banfield": "Lomas de Zamora",
}


def zona_de(record: dict) -> str:
    partido = record.get("partido")
    provincia = record.get("provincia") or ""
    if provincia and "autonoma" in provincia.lower():
        return "CABA"
    if partido in ("Lanús",):
        return "Lanús"
    if partido in ("Lomas de Zamora",):
        return "Lomas de Zamora"
    return "Resto"
