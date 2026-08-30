# Property Intelligence & Geolocation Pipeline

*[Read this in English ↓](#english)*

Un pipeline en Python que consolida publicaciones inmobiliarias
scrapeadas de múltiples portales, normaliza datos heterogéneos,
resuelve conflictos entre fuentes y lo convierte todo en un dataset
geocodificado, limpio y listo para mapear.

> **Este repositorio usa exclusivamente datos ficticios o anonimizados.**
> Los datasets usados en el entorno operativo no forman parte de esta
> versión pública — ver [`docs/PRIVACY_AUDIT.md`](docs/PRIVACY_AUDIT.md)
> con la auditoría realizada antes de publicar.

## Problema

Los portales inmobiliarios exponen el mismo tipo de información
(precio, ambientes, superficie, dirección, amenities) en formatos
completamente distintos: algunos vía `schema.org` JSON-LD limpio,
otros vía blobs de estado propios del framework (ej. un `TransferState`
de Angular embebido en un `<script>`), otros solo como texto libre en
la descripción. Consolidar publicaciones de varios portales en un
único dataset confiable y consultable implica resolver tres problemas
a la vez: **extracción** (por portal), **normalización** (un solo
esquema para todos) y **confianza** (qué pasa cuando dos fuentes se
contradicen).

## Pipeline

```
URLs
  │
  ▼
Web Scraping                     requests → Playwright solo si hace falta
  │                               nunca intenta evadir CAPTCHA/login/anti-bot
  ▼
Extracción de datos estructurados  JSON-LD, meta OpenGraph, estado propio del
  │                               portal (ej. TransferState de Angular), breadcrumb schema.org
  ▼
Normalización de propiedad        tipo, precio, ambientes, superficie, antigüedad, amenities
  │
  ▼
Normalización de dirección        calle/número/localidad/partido/provincia,
  │                               detección de conflicto entre dato estructurado y texto libre
  ▼
Validación de calidad de datos    sanity checks, detección de página genérica, flags de revisión
  │
  ▼
Geocodificación                   coordenadas del sitio si son confiables, si no Nominatim
  │                               (OpenStreetMap) en 4 niveles decrecientes de precisión
  ▼
QA geoespacial                    rechaza coordenadas fuera de la provincia esperada,
  │                               nunca confía en un resultado solo porque el geocoder devolvió HTTP 200
  ▼
Mapa interactivo / GeoJSON / KML / CSV
```

## Destacado técnico

- **Python** de punta a punta.
- **Web scraping / RPA**: `requests` + `BeautifulSoup` primero,
  **Playwright** solo como fallback para páginas renderizadas con JS —
  nunca se usa para vencer detección anti-bot, solo para renderizar
  contenido normal del lado del cliente.
- **Extracción de datos estructurados**: JSON-LD/OpenGraph genérico de
  `schema.org`, más dos extractores específicos por portal, hechos por
  ingeniería inversa sobre páginas reales: uno que lee el blob de
  estado embebido de un framework (mucho más rico que su JSON-LD
  público), y otro que lee un bloque `BreadcrumbList` para
  categoría/localidad.
- **pandas** / **openpyxl** para I/O tabular.
- **Geocodificación con OpenStreetMap / Nominatim** con fallback de 4
  niveles (dirección exacta → aproximación por cuadra → solo calle →
  solo localidad) y validación geográfica dura (bounding box + chequeo
  de provincia esperada) — un `200 OK` del geocoder nunca se trata como
  prueba de que el resultado es correcto.
- **Mapa interactivo con Folium**, clustering de marcadores, color por
  tipo de propiedad, y un estilo visualmente distinto por nivel de
  precisión de dirección.
- **Exports GeoJSON / KML / CSV** para reutilizar en otras herramientas GIS.
- **Cache en disco + checkpoints JSON**: cada corrida reanuda donde
  quedó; una URL fallida nunca aborta el batch completo.
- **Tests automatizados** (pytest) que cubren casos límite de
  normalización, detección de conflictos y manejo de negaciones en
  texto libre.
- **Trazabilidad por diseño**: cada campo derivado lleva su propia
  etiqueta `_fuente`/`_source`, así siempre se puede saber si un valor
  fue extraído, inferido o geocodificado — y de cuál de dos fuentes en
  conflicto salió.

## Principio de diseño: dato faltante > dato incorrecto

El pipeline nunca inventa un valor que no esté explícito en la fuente.
Si una altura no se puede confirmar, queda en `null` — no se redondea,
no se adivina, no se completa con `0` por default. Cuando dos fuentes
se contradicen (ej. el campo estructurado del sitio dice una altura y
la descripción en texto libre dice otra), **se preservan ambas** como
campos separados y el registro queda marcado para revisión manual en
vez de elegir una a ciegas.

## Calidad de datos

**`address_precision`** — cuánto de la dirección se conoce realmente:

| Valor | Significado |
|---|---|
| `EXACT_ADDRESS` | Calle + altura confirmadas, con contexto de localidad/provincia |
| `BLOCK_APPROXIMATION` | Solo se conoce la altura aproximada a nivel de cuadra |
| `STREET_ONLY` | Calle identificada, sin altura utilizable |
| `LOCALITY_ONLY` | Solo localidad/partido/provincia, sin calle |
| `UNKNOWN` | No hay datos suficientes para ubicarla geográficamente |

Un punto `LOCALITY_ONLY` nunca se dibuja en el mapa como si fuera la
puerta exacta de una propiedad — ver la leyenda de precisión y el
estilo de marcadores en [`src/maps/map_config.py`](src/maps/map_config.py).

**`scrape_status`** — qué pasó realmente al intentar traer una publicación:

| Valor | Significado |
|---|---|
| `SUCCESS` | Publicación real, se extrajeron datos utilizables |
| `PARTIAL` | Se pudo acceder, pero no se extrajo ni precio ni una dirección real |
| `GENERIC_PAGE` | Terminó en la página institucional/de inicio de la inmobiliaria, no en una ficha real |
| `BLOCKED` | Se detectó un desafío anti-bot/CAPTCHA — nunca se intenta evadir, solo se registra |
| `NOT_FOUND` | HTTP 404 |
| `ERROR` | Falla inesperada (red, parseo) — se loguea, el batch continúa |

## Estructura

```
src/
    scraper/          fetch + extractores por dominio + armado de registro
    normalization/     normalización de propiedad y dirección
    geocoding/         cliente Nominatim + validadores geográficos
    maps/              constructor de mapa con Folium
    export/            GeoJSON / KML / CSV
    utils/             I/O de Excel, cache en disco, checkpoints, logging
tests/
examples/
    build_demo_map.py       regenera todo lo de abajo a partir de datos sintéticos
    propiedades_demo.csv
    propiedades_demo.geojson
    propiedades_demo.kml
    mapa_demo.html
docs/
    PRIVACY_AUDIT.md
main.py
requirements.txt
```

## Correr la demo

```bash
pip install -r requirements.txt
python -m pytest tests/ -q

python examples/build_demo_map.py   # regenera examples/mapa_demo.html y los exports
```

`main.py` expone el CLI completo que se usa en la versión operativa
(`audit | pilot | scrape | geocode | map | export | enrich_excel | all`),
incluido acá para mostrar la arquitectura real y reproducible — espera
una planilla de entrada privada que intencionalmente no está incluida
en este repositorio. La demo autocontenida y ejecutable es
`examples/build_demo_map.py`.

## Licencia

MIT — ver [`LICENSE`](LICENSE).

---

<a id="english"></a>
# Property Intelligence & Geolocation Pipeline

*[Leer en español ↑](#property-intelligence--geolocation-pipeline)*

## Problem

Real-estate portals expose the same kind of information (price, rooms,
surface, address, amenities) in completely different formats: some via
clean `schema.org` JSON-LD, some via framework-specific state blobs
(e.g. an Angular `TransferState` script tag), some only as free text in
a description field. Consolidating listings from several portals into
one reliable, queryable dataset means solving three problems at once:
**extraction** (per-portal), **normalization** (one schema for
everyone), and **trust** (what happens when two sources disagree).

## Pipeline

```
URLs
  │
  ▼
Web Scraping                     requests → Playwright fallback only if needed
  │                               never attempts to bypass CAPTCHA/login/anti-bot
  ▼
Structured Data Extraction       JSON-LD, OpenGraph meta, per-portal state (e.g. Angular
  │                               TransferState), breadcrumb schema.org
  ▼
Property Normalization           type, price, rooms, surface, age, amenities
  │
  ▼
Address Normalization            street/number/locality/district/province,
  │                               conflict detection between structured data and free text
  ▼
Data Quality Validation          sanity checks, generic-page detection, manual-review flags
  │
  ▼
Geocoding                        site-provided coordinates when trustworthy, else Nominatim
  │                               (OpenStreetMap) across 4 decreasing precision levels
  ▼
Geospatial QA                    rejects coordinates outside the expected province,
  │                               never trusts a result just because the geocoder returned HTTP 200
  ▼
Interactive Map / GeoJSON / KML / CSV
```

## Highlights

- **Python** end to end.
- **Web scraping / RPA**: `requests` + `BeautifulSoup` first, **Playwright**
  only as a fallback for JS-rendered pages — never used to defeat
  bot-detection, only to render normal client-side content.
- **Structured data extraction**: generic `schema.org` JSON-LD/OpenGraph,
  plus two portal-specific extractors reverse-engineered from real
  pages: one that reads a framework's embedded state blob for far
  richer fields than its public JSON-LD exposes, and one that reads a
  `BreadcrumbList` block for category/locality.
- **pandas** / **openpyxl** for tabular I/O.
- **OpenStreetMap / Nominatim** geocoding with a 4-level fallback
  (exact address → block approximation → street only → locality only)
  and hard geographic validation (bounding box + expected-province
  check) — a `200 OK` from the geocoder is never treated as proof the
  result is correct.
- **Folium** interactive map with marker clustering, per-type color
  coding, and a visually distinct style per address-precision level.
- **GeoJSON / KML / CSV** exports for reuse in other GIS tools.
- **Disk cache + JSON checkpoints**: every run resumes from where it
  left off; a failed URL never aborts the batch.
- **Automated tests** (pytest) covering normalization edge cases,
  conflict detection, and negation handling in free text.
- **Traceability by design**: every derived field carries its own
  `_fuente`/`_source` tag, so you can always tell whether a value was
  extracted, inferred, or geocoded — and from which of two disagreeing
  sources it came.

## Design principle: missing data > incorrect data

The pipeline never invents a value that isn't explicit in the source.
If a street number can't be confirmed, it stays `null` — it does not
get rounded, guessed, or defaulted to `0`. When two sources disagree
(e.g. a site's structured field says one street number, the free-text
description says another), **both are preserved** as separate fields
and the record is flagged for manual review instead of silently
picking one.

## Data Quality

**`address_precision`** — how much of the address is actually known:

| Value | Meaning |
|---|---|
| `EXACT_ADDRESS` | Street + number confirmed, with locality/province context |
| `BLOCK_APPROXIMATION` | Only a block-level number is known (e.g. "at the 1200 block") |
| `STREET_ONLY` | Street identified, no usable number |
| `LOCALITY_ONLY` | Only locality/district/province, no street |
| `UNKNOWN` | Not enough data to place it geographically |

A `LOCALITY_ONLY` point is never rendered on the map as if it were an
exact front door — see the map's own precision legend and marker
styling in [`src/maps/map_config.py`](src/maps/map_config.py).

**`scrape_status`** — what actually happened when fetching a listing:

| Value | Meaning |
|---|---|
| `SUCCESS` | Real listing, usable data extracted |
| `PARTIAL` | Fetched, but neither price nor a real address could be extracted |
| `GENERIC_PAGE` | Landed on an agency's institutional/home page, not an actual listing |
| `BLOCKED` | Anti-bot / CAPTCHA challenge detected — never bypassed, just recorded |
| `NOT_FOUND` | HTTP 404 |
| `ERROR` | Unexpected failure (network, parsing) — logged, batch continues |

## Structure

```
src/
    scraper/          fetch + per-domain extractors + record builder
    normalization/     property and address normalization
    geocoding/         Nominatim client + geographic validators
    maps/              Folium map builder
    export/            GeoJSON / KML / CSV
    utils/             excel I/O, disk cache, checkpoints, logging
tests/
examples/
    build_demo_map.py       regenerates everything below from synthetic data
    propiedades_demo.csv
    propiedades_demo.geojson
    propiedades_demo.kml
    mapa_demo.html
docs/
    PRIVACY_AUDIT.md
main.py
requirements.txt
```

## Running the demo

```bash
pip install -r requirements.txt
python -m pytest tests/ -q

python examples/build_demo_map.py   # regenerates examples/mapa_demo.html and the exports
```

`main.py` exposes the full CLI used in the operational version
(`audit | pilot | scrape | geocode | map | export | enrich_excel | all`),
kept here to show the real, reproducible architecture — it expects a
private input spreadsheet that is intentionally not included in this
repository. The runnable, self-contained demo is `examples/build_demo_map.py`.

## License

MIT — see [`LICENSE`](LICENSE).
