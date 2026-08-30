"""Elige qué scraper de dominio usar según la URL de la publicación."""

from urllib.parse import urlparse

from src.scraper import remax_scraper, mercadolibre_scraper, buscadorprop_scraper, generic_scraper


def route(url: str):
    domain = urlparse(url).netloc.lower()
    if "remax.com.ar" in domain:
        return remax_scraper
    if "mercadolibre.com.ar" in domain:
        return mercadolibre_scraper
    if "buscadorprop.com.ar" in domain:
        return buscadorprop_scraper
    return generic_scraper


def scrape_row(planilla_row: dict, use_cache: bool = True) -> dict:
    scraper_module = route(planilla_row["URL"])
    return scraper_module.scrape(planilla_row, use_cache=use_cache)
