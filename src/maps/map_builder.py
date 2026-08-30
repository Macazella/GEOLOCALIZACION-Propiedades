"""
Construye mapa_propiedades.html con Folium: clustering, colores por tipo,
distinción visual por precisión geográfica, filtros por tipo y por zona,
y popup completo por propiedad (incluye comentario personal íntegro).
"""

import folium
from folium.plugins import MarkerCluster

from src.maps.map_config import COLOR_POR_TIPO, ICONO_POR_TIPO, PRECISION_STYLE, zona_de


def _formato_precio(record: dict) -> str:
    if record.get("precio") is None:
        return "No informado"
    moneda = record.get("moneda") or ""
    return f"{moneda} {record['precio']:,}".replace(",", ".")


def _formato_bool(valor) -> str:
    if valor is True:
        return "Sí"
    if valor is False:
        return "No"
    return "No informado"


def _formato_apto_credito(record: dict) -> str:
    """
    Usa apto_credito_final (no el viejo campo "apto_credito" que ya no
    existe desde el rediseño v2 de conflictos estructurado/texto — quedó
    reemplazado por apto_credito_structured/_text/_final/_conflict). Si
    hubo conflicto entre la fuente estructurada y el texto, se lo deja
    explícito en vez de mostrar un valor sin matices.
    """
    valor = _formato_bool(record.get("apto_credito_final"))
    if record.get("apto_credito_conflict"):
        return f"{valor} (⚠ dato en conflicto entre sitio y texto — ver revisión manual)"
    return valor


def _popup_html(record: dict) -> str:
    comentario = record.get("comentario_personal")
    comentario_html = (
        f"<p><strong>Comentario de Maga:</strong><br>\"{comentario}\"</p>" if comentario else ""
    )
    precision_label = PRECISION_STYLE.get(record.get("address_precision", ""), {}).get("label", "Desconocida")

    return f"""
    <div style="max-width:280px; font-family: Arial, sans-serif; font-size: 13px;">
        <p><strong>Tipo:</strong> {record.get('tipo_propiedad_original') or record.get('tipo_propiedad_normalizado') or '-'}</p>
        <p><strong>Título:</strong> {record.get('titulo_publicacion') or '-'}</p>
        <p><strong>Dirección:</strong> {record.get('calle') or '-'} {record.get('numero') or ''}</p>
        <p><strong>Localidad/Barrio:</strong> {record.get('localidad') or '-'}</p>
        <p><strong>Partido:</strong> {record.get('partido') or '-'}</p>
        <p><strong>Provincia:</strong> {record.get('provincia') or '-'}</p>
        <p><strong>Precio:</strong> {_formato_precio(record)}</p>
        <p><strong>Expensas:</strong> {record.get('expensas') or 'Sin datos'}</p>
        <p><strong>Ambientes:</strong> {record.get('ambientes') or 'No informado'}</p>
        <p><strong>Superficie:</strong> {f"{record['superficie_total_m2']} m2" if record.get('superficie_total_m2') else 'No informado'}</p>
        <p><strong>Apto crédito:</strong> {_formato_apto_credito(record)}</p>
        {comentario_html}
        <p><strong>Inmobiliaria:</strong> {record.get('fuente') or '-'}</p>
        <p><strong>Precisión geográfica:</strong> {precision_label}</p>
        <p><a href="{record.get('url')}" target="_blank" rel="noopener">VER PUBLICACIÓN →</a></p>
    </div>
    """


def build_map(records: list[dict], output_path: str) -> None:
    geolocated = [r for r in records if r.get("latitude") is not None and r.get("longitude") is not None]

    if not geolocated:
        center = [-34.7, -58.4]  # zona sur de Buenos Aires como fallback
    else:
        center = [
            sum(r["latitude"] for r in geolocated) / len(geolocated),
            sum(r["longitude"] for r in geolocated) / len(geolocated),
        ]

    fmap = folium.Map(location=center, zoom_start=12, tiles="OpenStreetMap")

    # Una capa (FeatureGroup) por tipo y por zona para poder filtrar
    capas_tipo = {t: folium.FeatureGroup(name=f"Tipo: {t}", show=True) for t in COLOR_POR_TIPO}
    cluster_por_tipo = {t: MarkerCluster().add_to(capas_tipo[t]) for t in COLOR_POR_TIPO}

    for record in geolocated:
        tipo = record.get("tipo_propiedad_normalizado", "OTRO")
        precision = record.get("address_precision", "LOCALITY_ONLY")
        style = PRECISION_STYLE.get(precision, PRECISION_STYLE["LOCALITY_ONLY"])
        color = COLOR_POR_TIPO.get(tipo, "gray")
        icono = ICONO_POR_TIPO.get(tipo, "question")

        popup = folium.Popup(_popup_html(record), max_width=320)

        marker = folium.Marker(
            location=[record["latitude"], record["longitude"]],
            popup=popup,
            tooltip=record.get("titulo_publicacion") or record.get("url"),
            icon=folium.Icon(color=color, icon=icono, prefix="fa"),
            opacity=style["opacity"],
        )
        marker.add_to(cluster_por_tipo.get(tipo, cluster_por_tipo["OTRO"]))

        # Si la precisión es aproximada, agregamos un círculo que comunique
        # la incertidumbre — nunca debe aparentar ser un domicilio exacto.
        if style["radius_m"]:
            folium.Circle(
                location=[record["latitude"], record["longitude"]],
                radius=style["radius_m"],
                color=color,
                fill=True,
                fill_opacity=0.08,
                weight=1,
                dash_array="5",
            ).add_to(cluster_por_tipo.get(tipo, cluster_por_tipo["OTRO"]))

    for capa in capas_tipo.values():
        capa.add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)

    # Leyenda simple de precisión geográfica
    leyenda_html = """
    <div style="position: fixed; bottom: 30px; left: 10px; z-index: 9999;
                background: white; padding: 10px; border: 1px solid #999;
                border-radius: 6px; font-family: Arial; font-size: 12px;">
        <strong>Precisión geográfica</strong><br>
        ● Opacidad plena = dirección exacta<br>
        ○ Círculo punteado = aproximado (cuadra/calle/localidad)<br>
        Verde = Casa · Naranja = PH · Azul = Depto · Gris = Otro
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(leyenda_html))

    fmap.save(output_path)
