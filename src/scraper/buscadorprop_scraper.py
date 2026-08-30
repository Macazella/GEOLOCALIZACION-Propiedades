"""
Scraper específico de BuscadorProp (www.buscadorprop.com.ar), un
agregador de propiedades. Delega en el pipeline genérico por ahora.
"""

from src.scraper.record_builder import build_record

DOMAIN = "buscadorprop.com.ar"


def scrape(planilla_row: dict, use_cache: bool = True) -> dict:
    record = build_record(planilla_row, use_cache=use_cache)
    record["fuente_dominio"] = DOMAIN
    return record
