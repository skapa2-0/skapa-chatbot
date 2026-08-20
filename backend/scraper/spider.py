"""Parcourt un site et récupère le HTML de ses pages internes.

Crawl en largeur, limité au même domaine que l'URL de départ, avec un
délai entre les requêtes pour ne pas surcharger le serveur cible.

Deux modes de récupération :

- `requests` (par défaut) : rapide, suffisant pour du HTML rendu côté serveur.
- Playwright (`render=True`) : lance un vrai navigateur Chromium et attend
  l'exécution du JavaScript. Indispensable pour les SPA (React/Vue/Angular)
  dont le HTML servi ne contient qu'un `<div id="root"></div>` vide.

Le choix se fait automatiquement (cf. `source_detector.needs_javascript`),
ou se force avec `SCRAPER_RENDER_JS=always|never` dans le `.env`.
"""
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from app.config import Config

# Extensions de fichiers binaires/média : inutile de les crawler comme des pages.
_SKIPPED_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".zip", ".mp4", ".mp3", ".woff", ".woff2", ".ttf",
)


def _headers() -> dict:
    return {"User-Agent": Config.SCRAPER_USER_AGENT}


def _same_domain(base_url: str, url: str) -> bool:
    return urlparse(base_url).netloc == urlparse(url).netloc


def _is_crawlable(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    return not urlparse(url).path.lower().endswith(_SKIPPED_EXTENSIONS)


def fetch_one(url: str, render: bool = False) -> str | None:
    """Récupère le HTML d'une seule page (avec ou sans exécution du JavaScript)."""
    if render:
        return render_page(url)

    try:
        response = requests.get(url, headers=_headers(), timeout=Config.INGEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException:
        return None

    # Une page non-HTML (PDF, image...) atteinte par un lien : on l'ignore ici.
    if "html" not in response.headers.get("Content-Type", "text/html").lower():
        return None

    return response.text


def render_page(url: str) -> str | None:
    """Rend la page dans Chromium et retourne le DOM après exécution du JavaScript."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Rendu JS impossible : `pip install playwright && playwright install chromium`.")
        return None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(user_agent=Config.SCRAPER_USER_AGENT)
            try:
                page.goto(url, timeout=Config.SCRAPER_RENDER_TIMEOUT_MS, wait_until="domcontentloaded")
                # Laisse le temps aux appels XHR/fetch de peupler le DOM.
                page.wait_for_load_state("networkidle", timeout=Config.SCRAPER_RENDER_TIMEOUT_MS)
            except Exception:
                pass  # timeout réseau : on prend le DOM en l'état, souvent déjà utilisable
            html = page.content()
            browser.close()
            return html
    except Exception as exc:
        print(f"Rendu JS échoué sur {url} : {exc}")
        return None


def fetch_pages(
    start_url: str, max_pages: int = 30, delay: float = 0.5, render: bool = False
) -> list[tuple[str, str]]:
    """Retourne une liste de tuples (url, html) pour les pages visitées.

    `render=True` fait passer chaque page par Chromium : bien plus lent, donc
    réservé aux sites qui ne renvoient rien d'exploitable sans JavaScript.
    """
    to_visit = [start_url]
    visited: set[str] = set()
    pages: list[tuple[str, str]] = []

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        html = fetch_one(url, render=render)
        if not html:
            continue

        pages.append((url, html))

        soup = BeautifulSoup(html, "html.parser")
        for link in soup.find_all("a", href=True):
            full_url = urljoin(url, link["href"]).split("#")[0]
            if _is_crawlable(full_url) and _same_domain(start_url, full_url) and full_url not in visited:
                to_visit.append(full_url)

        if not render:
            time.sleep(delay)  # Playwright est déjà lent, pas besoin d'en rajouter

    return pages
