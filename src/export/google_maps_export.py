"""
Exports para reutilizar el dataset geolocalizado fuera de este proyecto:
- CSV simple listo para importar en Google My Maps.
- KML para Google My Maps / Google Earth / Google Maps.
- GeoJSON estándar para Leaflet, Mapbox, Power BI, análisis geoespacial.
"""

import csv
import json
from xml.sax.saxutils import escape


def _solo_geolocalizados(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("latitude") is not None and r.get("longitude") is not None]


def export_google_maps_csv(records: list[dict], path: str) -> None:
    """
    Google My Maps importa CSV con columnas de nombre + latitud/longitud +
    descripción. Usamos ese formato mínimo.
    """
    rows = _solo_geolocalizados(records)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Latitude", "Longitude", "Description", "URL"])
        for r in rows:
            nombre = r.get("titulo_publicacion") or r.get("tipo_propiedad_original") or "Propiedad"
            descripcion_partes = [
                f"Tipo: {r.get('tipo_propiedad_original') or '-'}",
                f"Localidad: {r.get('localidad') or '-'}",
                f"Precio: {r.get('moneda') or ''} {r.get('precio') or 'No informado'}",
                f"Precisión: {r.get('address_precision')}",
            ]
            if r.get("comentario_personal"):
                descripcion_partes.append(f"Comentario: {r['comentario_personal']}")
            writer.writerow(
                [nombre, r["latitude"], r["longitude"], " | ".join(descripcion_partes), r.get("url")]
            )


def export_kml(records: list[dict], path: str) -> None:
    rows = _solo_geolocalizados(records)
    placemarks = []
    for r in rows:
        nombre = escape(str(r.get("titulo_publicacion") or r.get("tipo_propiedad_original") or "Propiedad"))
        descripcion_lineas = [
            f"Tipo: {r.get('tipo_propiedad_original') or '-'}",
            f"Direccion: {r.get('calle') or ''} {r.get('numero') or ''}".strip(),
            f"Localidad: {r.get('localidad') or '-'} / Partido: {r.get('partido') or '-'}",
            f"Precio: {r.get('moneda') or ''} {r.get('precio') or 'No informado'}",
            f"Precision geografica: {r.get('address_precision')}",
            f"URL: {r.get('url')}",
        ]
        if r.get("comentario_personal"):
            descripcion_lineas.append(f"Comentario personal: {r['comentario_personal']}")
        descripcion = escape("\n".join(descripcion_lineas))

        placemarks.append(
            f"""<Placemark>
    <name>{nombre}</name>
    <description>{descripcion}</description>
    <Point><coordinates>{r['longitude']},{r['latitude']},0</coordinates></Point>
  </Placemark>"""
        )

    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>Propiedades Geolocalizadas</name>
  {''.join(placemarks)}
</Document>
</kml>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(kml)


def export_geojson(records: list[dict], path: str) -> None:
    rows = _solo_geolocalizados(records)
    features = []
    for r in rows:
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
                "properties": {
                    "tipo": r.get("tipo_propiedad_normalizado"),
                    "tipo_original": r.get("tipo_propiedad_original"),
                    "calle": r.get("calle"),
                    "numero": r.get("numero"),
                    "localidad": r.get("localidad"),
                    "partido": r.get("partido"),
                    "provincia": r.get("provincia"),
                    "precio": r.get("precio"),
                    "moneda": r.get("moneda"),
                    "expensas": r.get("expensas"),
                    "comentario_personal": r.get("comentario_personal"),
                    "address_precision": r.get("address_precision"),
                    "url": r.get("url"),
                },
            }
        )

    geojson = {"type": "FeatureCollection", "features": features}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False)
