"""
Scraper base: obtiene el HTML de una publicación probando, en orden de
costo creciente:

  1) requests (HTML estático, rápido, sin JS)
  2) si no hay JSON-LD ni metadata útil, recién ahí Playwright (navegador
     real, para sitios que arman el contenido con JavaScript)

No intenta evadir CAPTCHA, login ni bloqueos anti-bot: si los detecta,
marca SCRAPING_BLOQUEADO y no reintenta con otra técnica.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.utils.logging_utils import get_logger
from src.utils.cache import DiskCache

logger = get_logger("scraper")
_html_cache = DiskCache("scraping_html")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Señales ESPECÍFICAS de página de bloqueo/challenge, no de referencias
# incidentales (ej. un <script src="cdnjs.cloudflare.com/..."> es un CDN
# normal, no un bloqueo; un widget de reCAPTCHA en un formulario de
# contacto tampoco lo es). Cada frase acá es una que solo aparece en la
# página de challenge en sí, no en contenido legítimo de la publicación.
BLOCK_SIGNALS = [
    "acceso denegado a esta pagina",
    "verifica que no eres un robot",
    "unusual traffic from your computer network",
    "attention required! | cloudflare",
    "checking your browser before accessing",
    "cf-browser-verification",
    "just a moment...",
    "ray id:",
    "please verify you are a human",
    "pardon our interruption",
    "solicitud bloqueada",
]

# Una página de bloqueo real es casi siempre muy corta (unos pocos KB).
# Contenido legítimo de una ficha de propiedad normalmente supera esto
# por mucho, así que combinamos "señal específica" + "respuesta corta"
# para evitar falsos positivos por texto incidental en páginas largas.
BLOCK_MAX_LENGTH_HINT = 8000


@dataclass
class FetchResult:
    url: str
    scrape_status: str = "PENDING"  # SUCCESS, PARTIAL, BLOCKED, NOT_FOUND, ERROR
    http_status: Optional[int] = None
    scrape_method: Optional[str] = None  # JSON_LD, META, HTML, PLAYWRIGHT
    jsonld: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    html: Optional[str] = None
    error: Optional[str] = None
    from_cache: bool = False


def _is_blocked(html: str, status_code: Optional[int]) -> bool:
    if status_code in (403, 429, 503):
        return True
    if not html:
        return False
    lowered = html.lower()
    signal_hit = any(sig in lowered for sig in BLOCK_SIGNALS)
    # Solo lo consideramos bloqueo real si además la respuesta es corta
    # (una página de challenge, no una ficha de propiedad completa que
    # simplemente menciona algo parecido en un script o widget legítimo).
    return signal_hit and len(html) < BLOCK_MAX_LENGTH_HINT


def _extract_json_ld(soup: BeautifulSoup) -> list:
    blocks = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            blocks.extend(data)
        else:
            blocks.append(data)
    return blocks


def _extract_meta(soup: BeautifulSoup) -> dict:
    meta = {}
    for tag in soup.find_all("meta"):
        prop = tag.get("property") or tag.get("name")
        content = tag.get("content")
        if prop and content:
            meta[prop] = content
    return meta


def _fetch_static(url: str, timeout: int = 15) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "es-AR,es;q=0.9"}
    return requests.get(url, headers=headers, timeout=timeout)


def _fetch_with_playwright(url: str, timeout_ms: int = 20000) -> tuple[str, int]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT, locale="es-AR")
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)  # deja asentar contenido dinámico
            html = page.content()
        finally:
            browser.close()
    return html, 200


def fetch(url: str, use_cache: bool = True, retries: int = 2, delay_between_tries: float = 3.0) -> FetchResult:
    if use_cache and _html_cache.has(url):
        cached = _html_cache.get(url)
        cached["from_cache"] = True
        logger.info(f"[CACHE] {url}")
        return FetchResult(**cached)

    result = FetchResult(url=url)
    html: Optional[str] = None
    status_code: Optional[int] = None

    # --- Nivel 1: requests (estático) ---
    for attempt in range(retries + 1):
        try:
            resp = _fetch_static(url)
            status_code = resp.status_code
            if resp.status_code == 404:
                result.scrape_status = "NOT_FOUND"
                result.http_status = 404
                break
            if _is_blocked(resp.text, resp.status_code):
                result.scrape_status = "BLOCKED"
                result.http_status = resp.status_code
                logger.warning(f"SCRAPING_BLOQUEADO (estatico): {url}")
                break
            if resp.status_code == 200:
                html = resp.text
                result.scrape_method = "HTML"
                break
        except requests.RequestException as e:
            logger.warning(f"Intento {attempt + 1} fallo en {url}: {e}")
            time.sleep(delay_between_tries)

    # --- Evaluamos si con esto alcanza, o hace falta JS ---
    soup = BeautifulSoup(html, "lxml") if html else None
    jsonld = _extract_json_ld(soup) if soup else []
    meta = _extract_meta(soup) if soup else {}
    needs_js = html is None or (not jsonld and len(meta) < 3)

    # --- Nivel 2: Playwright, solo si hace falta y no está bloqueado ---
    if needs_js and result.scrape_status not in ("BLOCKED", "NOT_FOUND"):
        try:
            html_js, status_js = _fetch_with_playwright(url)
            if _is_blocked(html_js, status_js):
                result.scrape_status = "BLOCKED"
                result.http_status = status_js
                logger.warning(f"SCRAPING_BLOQUEADO (playwright): {url}")
            else:
                html = html_js
                status_code = status_js
                result.scrape_method = "PLAYWRIGHT"
                soup = BeautifulSoup(html, "lxml")
                jsonld = _extract_json_ld(soup)
                meta = _extract_meta(soup)
        except Exception as e:
            logger.error(f"Playwright fallo en {url}: {e}")
            if result.scrape_status == "PENDING":
                result.scrape_status = "ERROR"
                result.error = str(e)

    result.http_status = result.http_status or status_code
    if jsonld:
        result.scrape_method = "JSON_LD"
    result.jsonld = jsonld
    result.meta = meta
    result.html = html

    if html is None and result.scrape_status == "PENDING":
        result.scrape_status = "ERROR"
        result.error = result.error or "No se pudo obtener HTML por ningun metodo disponible"
    elif html is not None and result.scrape_status == "PENDING":
        result.scrape_status = "SUCCESS"

    if use_cache:
        _html_cache.set(url, asdict(result))

    return result
