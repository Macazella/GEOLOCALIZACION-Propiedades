"""
Scraper genérico para las ~13 inmobiliarias chicas (Coviella, Red
Gestionar, Gómez Lama Hnos., Carames, Gianni, Eduardo Fernández, Elisabet
Costa, Orlando Fernández, Koatz, Lesza, Rizzo, Alicia Modenesi, Civeira),
cada una con su propio sitio/plantilla. Se apoya 100% en JSON-LD/OpenGraph
porque no vale la pena mantener selectores CSS por sitio para 1-18
registros cada uno.
"""

from urllib.parse import urlparse

from src.scraper.record_builder import build_record


def get_domain(url: str) -> str:
    return urlparse(url).netloc


def scrape(planilla_row: dict, use_cache: bool = True) -> dict:
    record = build_record(planilla_row, use_cache=use_cache)
    record["fuente_dominio"] = get_domain(planilla_row["URL"])
    return record
