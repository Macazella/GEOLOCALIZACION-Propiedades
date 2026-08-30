# Property Intelligence & Geolocation Pipeline

A Python pipeline that consolidates real-estate listings scraped from
multiple portals, normalizes heterogeneous data, resolves conflicts
between sources, and turns everything into a clean, geocoded,
map-ready dataset.

> **This repository uses exclusively fictional or anonymized data.**
> The datasets used in the operational environment are not part of
> this public version — see [`docs/PRIVACY_AUDIT.md`](docs/PRIVACY_AUDIT.md)
> for the audit performed before publishing.

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
