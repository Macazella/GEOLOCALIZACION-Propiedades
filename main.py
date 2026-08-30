"""
Pipeline de geolocalización de propiedades.

Uso:
    python main.py audit
    python main.py pilot
    python main.py scrape
    python main.py geocode
    python main.py map
    python main.py export
    python main.py enrich_excel
    python main.py all
"""

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass  # Python < 3.7 o stream sin reconfigure(), no crítico

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.utils.excel_io import leer_planilla_principal, escribir_planilla_enriquecida, PROJECT_ROOT
from src.utils.checkpoint import CheckpointStore
from src.utils.dedup import find_duplicate_urls
from src.utils.logging_utils import get_logger
from src.scraper.router import scrape_row, route
from src.scraper.record_builder import _skeleton_record
from src.geocoding.geocoder import geocode_record, apply_geocode_review_reasons
from src.geocoding import validators
from src.maps.map_builder import build_map
from src.export.google_maps_export import export_google_maps_csv, export_kml, export_geojson

logger = get_logger("main")

DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_GEOCODED = PROJECT_ROOT / "data" / "geocoded"
OUTPUT_DIR = PROJECT_ROOT / "output"
REPORTS_DIR = PROJECT_ROOT / "reports"


def cmd_audit():
    registros = leer_planilla_principal()
    print(f"Registros leídos: {len(registros)}")
    print(f"URLs únicas: {len(set(r['URL'] for r in registros))}")
    duplicados = find_duplicate_urls(registros)
    print(f"URLs duplicadas: {len(duplicados)}")
    print("Ver auditoria_inicial.md para el detalle completo.")


def _seleccionar_muestra_piloto(registros: list[dict], por_dominio: int = 3) -> list[dict]:
    """Selecciona ~3 URLs de RE/MAX, MercadoLibre, BuscadorProp + varias
    inmobiliarias chicas distintas para el piloto."""
    grupos: dict[str, list[dict]] = {"remax.com.ar": [], "mercadolibre.com.ar": [], "buscadorprop.com.ar": [], "otros": []}

    for r in registros:
        domain = urlparse(r["URL"]).netloc.lower()
        if "remax.com.ar" in domain:
            grupos["remax.com.ar"].append(r)
        elif "mercadolibre.com.ar" in domain:
            grupos["mercadolibre.com.ar"].append(r)
        elif "buscadorprop.com.ar" in domain:
            grupos["buscadorprop.com.ar"].append(r)
        else:
            grupos["otros"].append(r)

    muestra = []
    muestra.extend(grupos["remax.com.ar"][:por_dominio])
    muestra.extend(grupos["mercadolibre.com.ar"][:por_dominio])
    muestra.extend(grupos["buscadorprop.com.ar"][:por_dominio])

    # inmobiliarias chicas: una por dominio distinto, hasta cubrir 4
    vistos = set()
    for r in grupos["otros"]:
        dom = urlparse(r["URL"]).netloc.lower()
        if dom not in vistos:
            muestra.append(r)
            vistos.add(dom)
        if len(vistos) >= 4:
            break

    return muestra


def cmd_pilot():
    registros = leer_planilla_principal()
    muestra = _seleccionar_muestra_piloto(registros)

    print(f"Piloto sobre {len(muestra)} URLs (sin tocar el resto de las {len(registros)}):\n")

    resultados = []
    tiempos = []

    for row in muestra:
        url = row["URL"]
        dominio = urlparse(url).netloc
        print(f"  -> {dominio} :: {url}")
        t0 = time.time()
        try:
            record = scrape_row(row, use_cache=True)
            geo = geocode_record(record, use_cache=True)
            record.update(geo)
            apply_geocode_review_reasons(record)
        except Exception as e:
            logger.error(f"Error en piloto para {url}: {e}")
            record = {"url": url, "scrape_status": "ERROR", "error": str(e)}
        elapsed = time.time() - t0
        tiempos.append(elapsed)
        record["_dominio"] = dominio
        record["_tiempo_segundos"] = round(elapsed, 2)
        resultados.append(record)
        print(f"     status={record.get('scrape_status')} method={record.get('scrape_method')} tiempo={elapsed:.1f}s")

    # --- Guardar resultados crudos (v2: mismas 13 URLs, tras los 12 ajustes) ---
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    with open(DATA_PROCESSED / "piloto_sample_v2.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False, default=str)

    _generar_reporte_piloto(resultados, tiempos)
    _generar_comparacion_v1_v2(resultados)


def _generar_reporte_piloto(resultados: list[dict], tiempos: list[float]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    por_dominio: dict[str, list[dict]] = {}
    for r in resultados:
        por_dominio.setdefault(r["_dominio"], []).append(r)

    campos_clave = [
        "titulo_publicacion", "precio", "moneda", "ambientes", "dormitorios",
        "superficie_total_m2", "address_normalized", "address_precision",
        "latitude", "longitude", "geocode_status",
    ]

    lineas = ["# Reporte del piloto de scraping (v2)\n"]
    lineas.append("Mismas 13 URLs del piloto v1, corridas después de los 12 ajustes pedidos tras la revisión.\n")
    lineas.append(f"URLs probadas: {len(resultados)}")
    lineas.append(f"Tiempo promedio por URL: {sum(tiempos) / len(tiempos):.1f}s\n" if tiempos else "")

    # --- Distribución de scrape_status (ahora incluye GENERIC_PAGE/PARTIAL) ---
    estados_count: dict[str, int] = {}
    for r in resultados:
        estado = r.get("scrape_status", "DESCONOCIDO")
        estados_count[estado] = estados_count.get(estado, 0) + 1
    lineas.append("## Distribución de scrape_status\n")
    for estado, cant in sorted(estados_count.items(), key=lambda kv: -kv[1]):
        lineas.append(f"- {estado}: {cant}/{len(resultados)}")
    lineas.append("")

    # --- Conflictos y revisión manual (nuevo en v2) ---
    con_conflicto_direccion = sum(1 for r in resultados if r.get("address_conflict"))
    con_conflicto_apto_credito = sum(1 for r in resultados if r.get("apto_credito_conflict"))
    con_superficie_invalidada = sum(
        1 for r in resultados if r.get("superficie_total_confidence") == "INVALIDA_INCONSISTENTE_CON_AMBIENTES"
    )
    con_revision_manual = sum(1 for r in resultados if r.get("needs_manual_review"))
    lineas.append("## Conflictos detectados y revisión manual (nuevo en v2)\n")
    lineas.append(f"- Conflicto de dirección (estructurada vs. texto): {con_conflicto_direccion}/{len(resultados)}")
    lineas.append(f"- Conflicto de apto_credito (estructurado vs. texto): {con_conflicto_apto_credito}/{len(resultados)}")
    lineas.append(f"- Superficie total invalidada por inconsistencia con ambientes: {con_superficie_invalidada}/{len(resultados)}")
    lineas.append(f"- Requieren revisión manual (needs_manual_review): {con_revision_manual}/{len(resultados)}")
    for r in resultados:
        if r.get("needs_manual_review"):
            lineas.append(f"  - {r.get('url')}: {', '.join(r.get('needs_manual_review_reasons', []))}")
    lineas.append("")

    lineas.append("## Resultado por dominio\n")
    for dominio, regs in por_dominio.items():
        lineas.append(f"### {dominio} ({len(regs)} probadas)\n")
        metodos = {r.get("scrape_method") for r in regs}
        lineas.append(f"- Método(s) usado(s): {', '.join(m for m in metodos if m) or 'ninguno'}")
        estados = {r.get("scrape_status") for r in regs}
        lineas.append(f"- Estado(s): {', '.join(estados)}")

        for campo in campos_clave:
            con_dato = sum(1 for r in regs if r.get(campo) not in (None, ""))
            lineas.append(f"  - {campo}: {con_dato}/{len(regs)} con dato")
        lineas.append("")

    lineas.append("## Ejemplo de registro enriquecido completo\n")
    ejemplo = next((r for r in resultados if r.get("scrape_status") == "SUCCESS"), resultados[0] if resultados else None)
    if ejemplo:
        lineas.append("```json")
        lineas.append(json.dumps(ejemplo, indent=2, ensure_ascii=False, default=str))
        lineas.append("```")

    reporte = "\n".join(lineas)
    with open(REPORTS_DIR / "piloto_report_v2.md", "w", encoding="utf-8") as f:
        f.write(reporte)

    print("\n" + "=" * 60)
    print("Reporte del piloto v2 guardado en reports/piloto_report_v2.md")
    print("=" * 60)


def _generar_comparacion_v1_v2(resultados_v2: list[dict]) -> None:
    """
    Compara el piloto v1 (pre-ajustes) contra v2 (post-ajustes) sobre las
    MISMAS 13 URLs, campo por campo en los puntos que la corrección pidió
    verificar explícitamente, más un resumen agregado.
    """
    v1_path = DATA_PROCESSED / "piloto_sample_v1.json"
    if not v1_path.exists():
        print("Aviso: no se encontró piloto_sample_v1.json, se omite la tabla comparativa.")
        return

    with open(v1_path, "r", encoding="utf-8") as f:
        resultados_v1 = json.load(f)

    v1_by_url = {r["url"]: r for r in resultados_v1}
    v2_by_url = {r["url"]: r for r in resultados_v2}

    lineas = ["# Comparación piloto V1 vs V2\n"]
    lineas.append(
        "Mismas 13 URLs. V1 = piloto original (antes de los 12 ajustes). "
        "V2 = piloto tras aplicar los ajustes pedidos.\n"
    )

    # --- Casos puntuales que la corrección pidió verificar explícitamente ---
    lineas.append("## Casos puntuales señalados en la corrección\n")
    lineas.append("| URL | Chequeo | V1 | V2 |")
    lineas.append("|---|---|---|---|")

    def _fila(url: str, chequeo: str, v1_val, v2_val):
        lineas.append(f"| {url[:60]}... | {chequeo} | {v1_val} | {v2_val} |")

    remax_urls = [u for u in v1_by_url if "remax.com.ar" in u]
    for u in remax_urls:
        r1, r2 = v1_by_url.get(u, {}), v2_by_url.get(u, {})
        _fila(u, "fuente de dirección/precio", r1.get("titulo_publicacion_fuente"), r2.get("titulo_publicacion_fuente"))
        _fila(u, "address_conflict (estructurada vs. texto)", "n/a (no existía)", r2.get("address_conflict"))
        _fila(u, "geocode_status si trae coordenadas del sitio", r1.get("geocode_status"), r2.get("geocode_status"))
        _fila(u, "anio_construccion / antiguedad_anios (separados)", r1.get("antiguedad"), f"{r2.get('anio_construccion')} / {r2.get('antiguedad_anios')}")
        _fila(u, "apto_credito_conflict", "n/a (no existía)", r2.get("apto_credito_conflict"))

    ml_urls = [u for u in v1_by_url if "mercadolibre.com.ar" in u]
    for u in ml_urls:
        r1, r2 = v1_by_url.get(u, {}), v2_by_url.get(u, {})
        _fila(u, "superficie_total_m2", r1.get("superficie_total_m2"), r2.get("superficie_total_m2"))
        _fila(u, "superficie_total_confidence", "n/a (no existía)", r2.get("superficie_total_confidence"))

    carames_url = next((u for u in v1_by_url if "carames" in u), None)
    if carames_url:
        r1, r2 = v1_by_url.get(carames_url, {}), v2_by_url.get(carames_url, {})
        _fila(carames_url, "scrape_status (página institucional)", r1.get("scrape_status"), r2.get("scrape_status"))
        _fila(carames_url, "scrape_status_motivo", "n/a (no existía)", r2.get("scrape_status_motivo"))
        _fila(carames_url, "tipo_propiedad_normalizado (fallback por URL)", r1.get("tipo_propiedad_normalizado"), r2.get("tipo_propiedad_normalizado"))

    lineas.append("")

    # --- Resumen agregado ---
    lineas.append("## Resumen agregado (13 URLs)\n")

    def _dist_estados(resultados):
        d: dict[str, int] = {}
        for r in resultados:
            d[r.get("scrape_status", "?")] = d.get(r.get("scrape_status", "?"), 0) + 1
        return d

    dist_v1 = _dist_estados(resultados_v1)
    dist_v2 = _dist_estados(resultados_v2)
    todos_estados = sorted(set(dist_v1) | set(dist_v2))
    lineas.append("| scrape_status | V1 | V2 |")
    lineas.append("|---|---|---|")
    for estado in todos_estados:
        lineas.append(f"| {estado} | {dist_v1.get(estado, 0)} | {dist_v2.get(estado, 0)} |")
    lineas.append("")

    lineas.append("| Métrica | V1 | V2 |")
    lineas.append("|---|---|---|")
    lineas.append(f"| Conflictos de dirección detectados | n/a (campo no existía) | {sum(1 for r in resultados_v2 if r.get('address_conflict'))} |")
    lineas.append(f"| Conflictos de apto_credito detectados | n/a (campo no existía) | {sum(1 for r in resultados_v2 if r.get('apto_credito_conflict'))} |")
    lineas.append(f"| Superficies invalidadas por inconsistencia | n/a (sin chequeo) | {sum(1 for r in resultados_v2 if r.get('superficie_total_confidence') == 'INVALIDA_INCONSISTENTE_CON_AMBIENTES')} |")
    lineas.append(f"| Registros needs_manual_review | {sum(1 for r in resultados_v1 if r.get('needs_manual_review'))} | {sum(1 for r in resultados_v2 if r.get('needs_manual_review'))} |")
    lineas.append(f"| Páginas SUCCESS (potencialmente sobreestimado en V1) | {dist_v1.get('SUCCESS', 0)} | {dist_v2.get('SUCCESS', 0)} |")
    lineas.append(f"| Páginas GENERIC_PAGE (detección nueva en V2) | {dist_v1.get('GENERIC_PAGE', 0)} | {dist_v2.get('GENERIC_PAGE', 0)} |")

    reporte = "\n".join(lineas)
    comparacion_path = REPORTS_DIR / "comparacion_v1_v2.md"
    with open(comparacion_path, "w", encoding="utf-8") as f:
        f.write(reporte)

    print(f"Tabla comparativa V1 vs V2 guardada en reports/{comparacion_path.name}")


SCRAPE_DELAY_RANGE = (1.5, 3.0)  # segundos de espera entre publicaciones, solo cuando NO viene de cache


def cmd_scrape():
    import random

    registros = leer_planilla_principal()
    checkpoint = CheckpointStore("scraping_progress.json")

    pendientes = [r for r in registros if not checkpoint.is_done(r["URL"])]
    print(f"{len(pendientes)} de {len(registros)} URLs pendientes de scraping.")

    for i, row in enumerate(pendientes, 1):
        url = row["URL"]
        try:
            record = scrape_row(row, use_cache=True)
            checkpoint.set(url, {"status": record["scrape_status"], "record": record})
            if not record.get("_from_cache"):
                time.sleep(random.uniform(*SCRAPE_DELAY_RANGE))
        except Exception as e:
            # scrape_row/build_record ya son defensivos y no deberían
            # tirar excepciones (ver record_builder._skeleton_record),
            # pero esto es la última red de seguridad: una URL fallida
            # JAMÁS debe hacer perder la fila del batch completo (regla
            # dura: 511 filas de entrada = 511 registros de salida).
            logger.error(f"Error inesperado scrapeando {url} (fuera de build_record): {e}")
            record = _skeleton_record(row, str(e))
            checkpoint.set(url, {"status": record["scrape_status"], "record": record})
        if i % 10 == 0:
            print(f"  {i}/{len(pendientes)} procesadas. Estado: {checkpoint.summary()}")

    print(f"Scraping finalizado. Resumen: {checkpoint.summary()}")


def _cargar_scraped() -> list[dict]:
    checkpoint = CheckpointStore("scraping_progress.json")
    resultados = []
    for url, v in checkpoint.data.items():
        if "record" in v:
            resultados.append(v["record"])
        else:
            # Red de seguridad final: si por lo que sea quedó un
            # checkpoint sin "record" (ej. de una corrida con una versión
            # vieja del código), igual se reconstruye un esqueleto en vez
            # de perder la fila silenciosamente.
            logger.warning(f"Checkpoint sin 'record' para {url}, se reconstruye esqueleto ERROR.")
            resultados.append(_skeleton_record({"URL": url}, v.get("error", "checkpoint sin record")))
    return resultados


def cmd_geocode():
    scraped = _cargar_scraped()
    checkpoint = CheckpointStore("geocoding_progress.json")

    print(f"Geocodificando {len(scraped)} registros...")
    resultados = []
    for i, record in enumerate(scraped, 1):
        url = record["url"]
        cached = checkpoint.get(url)
        # ERROR queda afuera a propósito (se reintenta en cada resume,
        # igual que en el checkpoint de scraping); todos los demás
        # estados terminales sí se reutilizan tal cual, sin volver a
        # pegarle a Nominatim.
        if cached and cached.get("status") in (
            "EXACT", "APPROXIMATE", "LOCALITY_ONLY", "NOT_FOUND",
            "SITE_PROVIDED", "SITE_PROVIDED_CONFLICTO",
        ):
            record.update(cached["geo"])
        else:
            geo = geocode_record(record, use_cache=True)
            record.update(geo)
            checkpoint.set(url, {"status": geo["geocode_status"], "geo": geo})
        apply_geocode_review_reasons(record)
        resultados.append(record)
        if i % 20 == 0:
            print(f"  {i}/{len(scraped)} geocodificadas.")

    DATA_GEOCODED.mkdir(parents=True, exist_ok=True)
    with open(DATA_GEOCODED / "propiedades_geocoded.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False, default=str)

    print(f"Geocodificación finalizada. Resumen: {checkpoint.summary()}")
    _reporte_geocodificacion(resultados)


def _reporte_geocodificacion(records: list[dict]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    total = len(records)
    por_estado = {}
    for r in records:
        estado = r.get("geocode_status", "NOT_FOUND")
        por_estado[estado] = por_estado.get(estado, 0) + 1

    genericas = validators.detect_generic_coordinate_reuse(records)

    lineas = ["# Reporte de geocodificación\n", f"Total: {total}\n"]
    for estado, cant in por_estado.items():
        pct = (cant / total * 100) if total else 0
        lineas.append(f"- {estado}: {cant} ({pct:.1f}%)")
    lineas.append(f"\nCoordenadas repetidas 5+ veces (posible geocodificación genérica): {len(genericas)}")
    lineas.append("\n## Casos que requieren revisión manual\n")
    for r in records:
        if r.get("needs_manual_review") or r.get("geocode_status") in ("NOT_FOUND", "ERROR"):
            lineas.append(f"- {r.get('url')} (scrape={r.get('scrape_status')}, geocode={r.get('geocode_status')})")

    with open(REPORTS_DIR / "reporte_geocodificacion.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))


def cmd_map():
    with open(DATA_GEOCODED / "propiedades_geocoded.json", "r", encoding="utf-8") as f:
        records = json.load(f)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    build_map(records, str(OUTPUT_DIR / "mapa_propiedades.html"))
    print(f"Mapa generado en {OUTPUT_DIR / 'mapa_propiedades.html'}")


def cmd_export():
    with open(DATA_GEOCODED / "propiedades_geocoded.json", "r", encoding="utf-8") as f:
        records = json.load(f)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export_geojson(records, str(OUTPUT_DIR / "propiedades_geolocalizadas.geojson"))
    export_google_maps_csv(records, str(OUTPUT_DIR / "propiedades_google_maps.csv"))
    export_kml(records, str(OUTPUT_DIR / "propiedades_google_maps.kml"))

    import csv

    with open(OUTPUT_DIR / "propiedades_geolocalizadas.csv", "w", newline="", encoding="utf-8") as f:
        if records:
            # Unión de columnas de TODOS los registros: los campos varían
            # por dominio (ej. latitude_sitio solo en RE/MAX), tomar solo
            # las del primer registro dejaría esas columnas afuera del
            # resto en silencio.
            fieldnames: list = []
            vistas = set()
            for r in records:
                for k in r.keys():
                    if k not in vistas:
                        vistas.add(k)
                        fieldnames.append(k)

            def _valor_csv(v):
                if isinstance(v, (dict, list)):
                    return json.dumps(v, ensure_ascii=False, default=str)
                return v

            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in records:
                writer.writerow({k: _valor_csv(v) for k, v in r.items()})

    print("Exports generados en output/")


def cmd_enrich_excel():
    with open(DATA_GEOCODED / "propiedades_geocoded.json", "r", encoding="utf-8") as f:
        records = json.load(f)

    errores = [r for r in records if r.get("scrape_status") == "ERROR"]
    bloqueados = [r for r in records if r.get("scrape_status") == "BLOCKED"]
    duplicados = find_duplicate_urls(records, url_key="url")

    total = len(records)
    estadisticas = [
        {"Métrica": "Total de propiedades", "Valor": total},
        {"Métrica": "Con geocodificación EXACT", "Valor": sum(1 for r in records if r.get("geocode_status") == "EXACT")},
        {"Métrica": "Con geocodificación APPROXIMATE", "Valor": sum(1 for r in records if r.get("geocode_status") == "APPROXIMATE")},
        {"Métrica": "Solo localidad", "Valor": sum(1 for r in records if r.get("geocode_status") == "LOCALITY_ONLY")},
        {"Métrica": "No encontradas", "Valor": sum(1 for r in records if r.get("geocode_status") == "NOT_FOUND")},
        {"Métrica": "Bloqueadas", "Valor": len(bloqueados)},
        {"Métrica": "Con error", "Valor": len(errores)},
        {"Métrica": "Requieren revisión manual", "Valor": sum(1 for r in records if r.get("needs_manual_review"))},
    ]

    hojas = {
        "PROPIEDADES_ENRIQUECIDAS": records,
        "SCRAPING_ERRORES": errores,
        "SCRAPING_BLOQUEADOS": bloqueados,
        "DUPLICADOS": duplicados,
        "ESTADISTICAS": estadisticas,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    escribir_planilla_enriquecida(hojas, str(OUTPUT_DIR / "Planilla_Propiedades_Enriquecida.xlsx"))
    print(f"Planilla enriquecida generada en {OUTPUT_DIR / 'Planilla_Propiedades_Enriquecida.xlsx'}")


def _validacion_final_y_reportes():
    """
    Controles globales + los 3 reportes finales pedidos para la corrida
    masiva (reporte_corrida_completa.md, casos_revision_manual.md,
    scraping_errores.md). No modifica nada del Excel original ni de los
    registros — es puramente de lectura/reporte sobre lo ya generado.
    """
    registros_entrada = leer_planilla_principal()
    urls_entrada = {r["URL"] for r in registros_entrada}

    with open(DATA_GEOCODED / "propiedades_geocoded.json", "r", encoding="utf-8") as f:
        records = json.load(f)
    urls_salida = {r.get("url") for r in records}

    faltantes = urls_entrada - urls_salida
    sobrantes = urls_salida - urls_entrada
    duplicados_salida = len(records) - len(urls_salida)

    total_entrada = len(registros_entrada)
    total_salida = len(records)

    def _count(pred):
        return sum(1 for r in records if pred(r))

    conteo_scrape_status = {}
    for r in records:
        st = r.get("scrape_status", "DESCONOCIDO")
        conteo_scrape_status[st] = conteo_scrape_status.get(st, 0) + 1

    conteo_precision = {}
    for r in records:
        p = r.get("address_precision", "DESCONOCIDA")
        conteo_precision[p] = conteo_precision.get(p, 0) + 1

    con_precio = _count(lambda r: r.get("precio") is not None)
    con_expensas = _count(lambda r: r.get("expensas") is not None)
    con_expensas_cero = _count(lambda r: r.get("expensas") == 0)
    con_calle = _count(lambda r: r.get("calle") not in (None, ""))
    con_calle_numero = _count(lambda r: r.get("calle") not in (None, "") and r.get("numero") not in (None, ""))
    con_localidad = _count(lambda r: r.get("localidad") not in (None, ""))
    con_coordenadas = _count(lambda r: r.get("latitude") is not None and r.get("longitude") is not None)
    con_revision_manual = _count(lambda r: r.get("needs_manual_review") is True)

    # --- Comentarios personales: verificación EXHAUSTIVA (no solo los 2
    #     casos de la mini-validación) contra el Excel original ---
    planilla_por_url = {r["URL"]: r for r in registros_entrada}
    comentarios_originales = {u: r.get("Comentario personal") for u, r in planilla_por_url.items() if r.get("Comentario personal")}
    comentarios_ok, comentarios_mal = 0, []
    for r in records:
        u = r.get("url")
        if u in comentarios_originales:
            if r.get("comentario_personal") == comentarios_originales[u]:
                comentarios_ok += 1
            else:
                comentarios_mal.append(u)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # ================= reporte_corrida_completa.md =================
    lineas = ["# Reporte de la corrida completa (511 propiedades)\n"]
    lineas.append(f"- Total de entrada (planilla original, hoja 'Ranking actualizado'): **{total_entrada}**")
    lineas.append(f"- Total de salida (registros enriquecidos): **{total_salida}**")
    if faltantes or sobrantes or duplicados_salida:
        lineas.append("\n**⚠ DISCREPANCIA ENTRE ENTRADA Y SALIDA — la corrida NO debe considerarse finalizada sin explicar esto:**\n")
        if faltantes:
            lineas.append(f"- URLs de la planilla que NO aparecen en la salida ({len(faltantes)}):")
            for u in sorted(faltantes):
                lineas.append(f"  - {u}")
        if sobrantes:
            lineas.append(f"- URLs en la salida que NO están en la planilla original ({len(sobrantes)}):")
            for u in sorted(sobrantes):
                lineas.append(f"  - {u}")
        if duplicados_salida:
            lineas.append(f"- Hay {duplicados_salida} registro(s) de salida con URL repetida.")
    else:
        lineas.append("\n✅ Sin discrepancias: cada URL de entrada tiene exactamente un registro de salida.\n")

    lineas.append("\n## Distribución de scrape_status\n")
    for estado in ("SUCCESS", "PARTIAL", "GENERIC_PAGE", "BLOCKED", "NOT_FOUND", "ERROR"):
        cant = conteo_scrape_status.get(estado, 0)
        pct = (cant / total_salida * 100) if total_salida else 0
        lineas.append(f"- {estado}: {cant} ({pct:.1f}%)")
    otros_estados = set(conteo_scrape_status) - {"SUCCESS", "PARTIAL", "GENERIC_PAGE", "BLOCKED", "NOT_FOUND", "ERROR"}
    for estado in otros_estados:
        lineas.append(f"- {estado} (no esperado): {conteo_scrape_status[estado]}")

    lineas.append("\n## Cobertura de campos\n")
    lineas.append(f"- Con precio: {con_precio}/{total_salida}")
    lineas.append(f"- Con expensas (dato real, no NULL): {con_expensas}/{total_salida} (de los cuales expensas=0 con evidencia real: {con_expensas_cero})")
    lineas.append(f"- Con calle: {con_calle}/{total_salida}")
    lineas.append(f"- Con calle+número: {con_calle_numero}/{total_salida}")
    lineas.append(f"- Con localidad: {con_localidad}/{total_salida}")
    lineas.append(f"- Con coordenadas (geocodificadas o del sitio): {con_coordenadas}/{total_salida}")

    lineas.append("\n## Precisión geográfica (address_precision)\n")
    for prec in ("EXACT_ADDRESS", "BLOCK_APPROXIMATION", "STREET_ONLY", "LOCALITY_ONLY", "UNKNOWN"):
        cant = conteo_precision.get(prec, 0)
        lineas.append(f"- {prec}: {cant}")

    lineas.append("\n## Revisión manual y comentarios personales\n")
    lineas.append(f"- Requieren revisión manual (needs_manual_review): {con_revision_manual}/{total_salida}")
    lineas.append(f"- Filas con comentario personal en el Excel original: {len(comentarios_originales)}")
    lineas.append(f"- Comentarios preservados EXACTOS en la salida: {comentarios_ok}/{len(comentarios_originales)}")
    if comentarios_mal:
        lineas.append(f"- ⚠ Comentarios que NO coinciden textualmente ({len(comentarios_mal)}):")
        for u in comentarios_mal:
            lineas.append(f"  - {u}")

    lineas.append(
        "\n## Ver también\n\n"
        "- reports/reporte_geocodificacion.md (detalle de geocodificación)\n"
        "- reports/casos_revision_manual.md (listado de needs_manual_review)\n"
        "- reports/scraping_errores.md (listado de BLOCKED/ERROR)\n"
        "- logs/pipeline.log (log completo de ejecución)\n"
    )

    with open(REPORTS_DIR / "reporte_corrida_completa.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))

    # ================= casos_revision_manual.md =================
    lineas_rm = ["# Casos que requieren revisión manual\n", f"Total: {con_revision_manual}\n"]
    for r in records:
        if r.get("needs_manual_review"):
            lineas_rm.append(f"## {r.get('url')}\n")
            lineas_rm.append(f"- Fuente: {r.get('fuente')}")
            lineas_rm.append(f"- scrape_status: {r.get('scrape_status')} ({r.get('scrape_status_motivo') or '-'})")
            lineas_rm.append(f"- Motivos: {', '.join(r.get('needs_manual_review_reasons') or [])}")
            if r.get("address_conflict"):
                lineas_rm.append(f"  - Conflicto de dirección: {r.get('address_conflict_details')}")
                lineas_rm.append(f"  - address_structured: {r.get('address_structured')}")
                lineas_rm.append(f"  - address_text: {r.get('address_text')}")
            if r.get("apto_credito_conflict"):
                lineas_rm.append(f"  - Conflicto apto_credito: {r.get('apto_credito_conflict_details')}")
            if r.get("geocode_status") in ("NOT_FOUND", "ERROR"):
                lineas_rm.append(f"  - Geocodificación: {r.get('geocode_status')}")
            lineas_rm.append("")

    with open(REPORTS_DIR / "casos_revision_manual.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lineas_rm))

    # ================= scraping_errores.md =================
    lineas_err = ["# Errores y bloqueos de scraping\n"]
    errores = [r for r in records if r.get("scrape_status") == "ERROR"]
    bloqueados = [r for r in records if r.get("scrape_status") == "BLOCKED"]
    not_found = [r for r in records if r.get("scrape_status") == "NOT_FOUND"]
    lineas_err.append(f"- ERROR: {len(errores)}")
    lineas_err.append(f"- BLOCKED (SCRAPING_BLOQUEADO): {len(bloqueados)}")
    lineas_err.append(f"- NOT_FOUND: {len(not_found)}\n")

    for titulo, grupo in [("ERROR", errores), ("BLOCKED", bloqueados), ("NOT_FOUND", not_found)]:
        lineas_err.append(f"## {titulo} ({len(grupo)})\n")
        for r in grupo:
            motivo = r.get("needs_manual_review_reasons") or []
            lineas_err.append(f"- {r.get('url')} — http_status={r.get('http_status')}, motivo={motivo}")
        lineas_err.append("")

    with open(REPORTS_DIR / "scraping_errores.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lineas_err))

    print("\n" + "=" * 70)
    print(f"VALIDACIÓN FINAL: entrada={total_entrada}, salida={total_salida}")
    if faltantes or sobrantes or duplicados_salida:
        print("⚠ DISCREPANCIA — ver reports/reporte_corrida_completa.md")
    else:
        print("✅ Sin discrepancias entre entrada y salida.")
    print(f"scrape_status: {conteo_scrape_status}")
    print(f"needs_manual_review: {con_revision_manual}/{total_salida}")
    print(f"Comentarios preservados: {comentarios_ok}/{len(comentarios_originales)}")
    print("Reportes: reporte_corrida_completa.md, casos_revision_manual.md, scraping_errores.md")
    print("=" * 70)


def cmd_all():
    cmd_scrape()
    cmd_geocode()
    cmd_map()
    cmd_export()
    cmd_enrich_excel()
    _validacion_final_y_reportes()


COMMANDS = {
    "audit": cmd_audit,
    "pilot": cmd_pilot,
    "scrape": cmd_scrape,
    "geocode": cmd_geocode,
    "map": cmd_map,
    "export": cmd_export,
    "enrich_excel": cmd_enrich_excel,
    "all": cmd_all,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline de geolocalización de propiedades")
    parser.add_argument("command", choices=list(COMMANDS.keys()))
    args = parser.parse_args()
    COMMANDS[args.command]()
