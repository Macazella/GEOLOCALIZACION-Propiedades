"""
Scraper específico de MercadoLibre Inmuebles (varios subdominios:
inmueble./departamento./casa./terreno.mercadolibre.com.ar).

MercadoLibre expone poco en el JSON-LD "Product" (solo precio/moneda),
pero el "BreadcrumbList" trae tipo + localidad ya limpios (ver
mercadolibre_extractor). Ambientes/dormitorios no vienen estructurados;
la descripción es de formato libre (dimensiones de cada ambiente en vez
de "N ambientes"), así que por ahora esos dos campos quedan en manos del
extractor genérico de texto (con menor cobertura, ver piloto_report.md).
"""

from src.scraper.record_builder import build_record
from src.scraper.mercadolibre_extractor import build_mercadolibre_fields

DOMAIN = "mercadolibre.com.ar"


def scrape(planilla_row: dict, use_cache: bool = True) -> dict:
    record = build_record(planilla_row, use_cache=use_cache, domain_overrides=build_mercadolibre_fields)
    record["fuente_dominio"] = DOMAIN
    return record
