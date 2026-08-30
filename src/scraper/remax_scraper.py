"""
Scraper específico de RE/MAX (remax.com.ar).

Usa remax_extractor para parsear el ng-state (Angular TransferState) que
trae precio, expensas, dirección exacta y coordenadas ya calculadas por
el sitio — mucho más completo que JSON-LD/meta genérico, que RE/MAX no
expone para estos datos.
"""

from src.scraper.record_builder import build_record
from src.scraper.remax_extractor import build_remax_fields

DOMAIN = "remax.com.ar"


def scrape(planilla_row: dict, use_cache: bool = True) -> dict:
    record = build_record(planilla_row, use_cache=use_cache, domain_overrides=build_remax_fields)
    record["fuente_dominio"] = DOMAIN
    return record
