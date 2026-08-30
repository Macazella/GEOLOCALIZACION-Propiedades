"""
Genera los artefactos de demo (CSV / GeoJSON / KML / mapa Folium) a
partir de un dataset 100% ficticio, usando el mismo código de
producción (src/maps, src/export) que usa el pipeline real.

Ningún dato de este archivo proviene del dataset operativo privado:
direcciones, comentarios, coordenadas y URLs son sintéticos e
inequívocamente falsos (Calle Demo, Avenida Ejemplo, Pasaje Ficticio,
localidad.example, etc.).

Uso:
    python examples/build_demo_map.py
"""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.maps.map_builder import build_map
from src.export.google_maps_export import export_geojson, export_kml

EXAMPLES_DIR = Path(__file__).resolve().parent

# Coordenadas ficticias en una zona amplia y despoblada (no corresponden
# a ninguna dirección real) para que el mapa se pueda abrir sin depender
# de red ni de un geocoder real.
DEMO_RECORDS = [
    {
        "url": "https://demo.example.com/propiedad/1",
        "fuente": "Portal Demo A",
        "titulo_publicacion": "Casa 3 ambientes con patio — DEMO",
        "tipo_propiedad_original": "Casa",
        "tipo_propiedad_normalizado": "CASA",
        "calle": "Calle Demo",
        "numero": "123",
        "localidad": "Localidad Ejemplo",
        "partido": "Partido Ejemplo",
        "provincia": "Provincia Ficticia",
        "address_normalized": "Calle Demo 123, Localidad Ejemplo, Partido Ejemplo, Provincia Ficticia",
        "address_precision": "EXACT_ADDRESS",
        "address_conflict": False,
        "precio": 120000,
        "moneda": "USD",
        "expensas": None,
        "ambientes": 3,
        "superficie_total_m2": 90,
        "apto_credito_final": True,
        "apto_credito_conflict": False,
        "comentario_personal": "Ejemplo de comentario del usuario",
        "scrape_status": "SUCCESS",
        "needs_manual_review": False,
        "latitude": -41.1000, "longitude": -71.3000,
    },
    {
        "url": "https://demo.example.com/propiedad/2",
        "fuente": "Portal Demo B",
        "titulo_publicacion": "PH 2 ambientes reciclado — DEMO",
        "tipo_propiedad_original": "PH",
        "tipo_propiedad_normalizado": "PH",
        "calle": "Avenida Ejemplo",
        "numero": "456",
        "localidad": "Localidad Ejemplo",
        "partido": "Partido Ejemplo",
        "provincia": "Provincia Ficticia",
        "address_normalized": "Avenida Ejemplo 456 (altura aproximada), Localidad Ejemplo, Provincia Ficticia",
        "address_precision": "BLOCK_APPROXIMATION",
        "address_conflict": False,
        "precio": 85000,
        "moneda": "USD",
        "expensas": 15000,
        "ambientes": 2,
        "superficie_total_m2": 55,
        "apto_credito_final": None,
        "apto_credito_conflict": False,
        "comentario_personal": None,
        "scrape_status": "SUCCESS",
        "needs_manual_review": False,
        "latitude": -41.1050, "longitude": -71.3050,
    },
    {
        "url": "https://demo.example.com/propiedad/3",
        "fuente": "Portal Demo A",
        "titulo_publicacion": "Departamento 1 ambiente — DEMO",
        "tipo_propiedad_original": "Departamento",
        "tipo_propiedad_normalizado": "DEPARTAMENTO",
        "calle": "Pasaje Ficticio",
        "numero": None,
        "localidad": "Localidad Ejemplo",
        "partido": "Partido Ejemplo",
        "provincia": "Provincia Ficticia",
        "address_normalized": "Pasaje Ficticio, Localidad Ejemplo, Provincia Ficticia",
        "address_precision": "STREET_ONLY",
        "address_conflict": False,
        "precio": 45000,
        "moneda": "USD",
        "expensas": 0,  # evidencia real: la publicación DEMO dice explícitamente "sin expensas"
        "ambientes": 1,
        "superficie_total_m2": 30,
        "apto_credito_final": False,
        "apto_credito_conflict": False,
        "comentario_personal": "Propiedad de demostración",
        "scrape_status": "SUCCESS",
        "needs_manual_review": False,
        "latitude": -41.1100, "longitude": -71.3100,
    },
    {
        "url": "https://demo.example.com/propiedad/4",
        "fuente": "Portal Demo C",
        "titulo_publicacion": None,
        "tipo_propiedad_original": None,
        "tipo_propiedad_normalizado": "OTRO",
        "calle": None,
        "numero": None,
        "localidad": "Localidad Ejemplo",
        "partido": "Partido Ejemplo",
        "provincia": "Provincia Ficticia",
        "address_normalized": "Localidad Ejemplo, Partido Ejemplo, Provincia Ficticia",
        "address_precision": "LOCALITY_ONLY",
        "address_conflict": False,
        "precio": None,
        "moneda": None,
        "expensas": None,
        "ambientes": None,
        "superficie_total_m2": None,
        "apto_credito_final": None,
        "apto_credito_conflict": False,
        "comentario_personal": None,
        "scrape_status": "PARTIAL",
        "needs_manual_review": True,
        "needs_manual_review_reasons": ["scrape_status=PARTIAL"],
        "latitude": -41.1150, "longitude": -71.3150,
    },
    {
        "url": "https://demo.example.com/propiedad/5",
        "fuente": "Portal Demo B",
        "titulo_publicacion": "Casa a reciclar con conflicto de altura — DEMO",
        "tipo_propiedad_original": "Casa",
        "tipo_propiedad_normalizado": "CASA",
        "calle": "Calle Demo",
        "numero": "900",
        "localidad": "Localidad Ejemplo",
        "partido": "Partido Ejemplo",
        "provincia": "Provincia Ficticia",
        "address_normalized": "Calle Demo 900 (aproximado por conflicto), Localidad Ejemplo, Provincia Ficticia",
        "address_precision": "BLOCK_APPROXIMATION",
        "address_conflict": True,
        "address_conflict_details": "numero_estructurado=900 vs numero_texto=950",
        "precio": 98000,
        "moneda": "USD",
        "expensas": None,
        "ambientes": 3,
        "superficie_total_m2": 110,
        "apto_credito_final": True,
        "apto_credito_conflict": True,
        "apto_credito_conflict_details": "estructurado=True vs texto=False",
        "comentario_personal": "Ejemplo anonimizado",
        "scrape_status": "SUCCESS",
        "needs_manual_review": True,
        "needs_manual_review_reasons": ["conflicto_direccion", "conflicto_apto_credito"],
        "latitude": -41.1200, "longitude": -71.3200,
    },
    {
        "url": "https://demo.example.com/propiedad/6",
        "fuente": "Portal Demo A",
        "titulo_publicacion": "Portal Demo A — Institucional",
        "tipo_propiedad_original": None,
        "tipo_propiedad_normalizado": "OTRO",
        "calle": None, "numero": None,
        "localidad": None, "partido": None, "provincia": None,
        "address_normalized": None,
        "address_precision": "UNKNOWN",
        "address_conflict": False,
        "precio": None, "moneda": None, "expensas": None,
        "ambientes": None, "superficie_total_m2": None,
        "apto_credito_final": None, "apto_credito_conflict": False,
        "comentario_personal": None,
        "scrape_status": "GENERIC_PAGE",
        "scrape_status_motivo": "titulo_parece_pagina_institucional",
        "needs_manual_review": True,
        "needs_manual_review_reasons": ["scrape_status=GENERIC_PAGE"],
        "latitude": None, "longitude": None,
    },
    {
        "url": "https://demo.example.com/propiedad/7",
        "fuente": "Portal Demo C",
        "titulo_publicacion": None,
        "tipo_propiedad_original": None,
        "tipo_propiedad_normalizado": "OTRO",
        "calle": None, "numero": None, "localidad": None, "partido": None, "provincia": None,
        "address_normalized": None,
        "address_precision": "UNKNOWN",
        "address_conflict": False,
        "precio": None, "moneda": None, "expensas": None,
        "ambientes": None, "superficie_total_m2": None,
        "apto_credito_final": None, "apto_credito_conflict": False,
        "comentario_personal": None,
        "scrape_status": "BLOCKED",
        "needs_manual_review": True,
        "needs_manual_review_reasons": ["scrape_status=BLOCKED"],
        "latitude": None, "longitude": None,
    },
    {
        "url": "https://demo.example.com/propiedad/8",
        "fuente": "Portal Demo B",
        "titulo_publicacion": None,
        "tipo_propiedad_original": None,
        "tipo_propiedad_normalizado": "OTRO",
        "calle": None, "numero": None, "localidad": None, "partido": None, "provincia": None,
        "address_normalized": None,
        "address_precision": "UNKNOWN",
        "address_conflict": False,
        "precio": None, "moneda": None, "expensas": None,
        "ambientes": None, "superficie_total_m2": None,
        "apto_credito_final": None, "apto_credito_conflict": False,
        "comentario_personal": None,
        "scrape_status": "NOT_FOUND",
        "needs_manual_review": True,
        "needs_manual_review_reasons": ["scrape_status=NOT_FOUND"],
        "latitude": None, "longitude": None,
    },
]


def main():
    # CSV simple con el dataset demo (no pasa por el pipeline de scraping,
    # es el dataset "de entrada" ilustrativo)
    demo_csv_path = EXAMPLES_DIR / "propiedades_demo.csv"
    campos = [
        "url", "fuente", "titulo_publicacion", "tipo_propiedad_normalizado",
        "calle", "numero", "localidad", "partido", "provincia",
        "address_precision", "precio", "moneda", "expensas", "ambientes",
        "superficie_total_m2", "apto_credito_final", "comentario_personal",
        "scrape_status", "needs_manual_review", "latitude", "longitude",
    ]
    with open(demo_csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        for r in DEMO_RECORDS:
            w.writerow({k: r.get(k) for k in campos})
    print(f"CSV demo generado: {demo_csv_path}")

    geojson_path = EXAMPLES_DIR / "propiedades_demo.geojson"
    export_geojson(DEMO_RECORDS, str(geojson_path))
    print(f"GeoJSON demo generado: {geojson_path}")

    kml_path = EXAMPLES_DIR / "propiedades_demo.kml"
    export_kml(DEMO_RECORDS, str(kml_path))
    print(f"KML demo generado: {kml_path}")

    map_path = EXAMPLES_DIR / "mapa_demo.html"
    build_map(DEMO_RECORDS, str(map_path))
    print(f"Mapa demo generado: {map_path}")


if __name__ == "__main__":
    main()
