"""
Spider ultra simple : part de SCRAPER_TARGET_URL, suit les liens internes
(même domaine) et récupère le HTML de chaque page.

Pas de JS ici -> requests + BeautifulSoup. Si un site charge son contenu
en JavaScript et que le texte n'apparaît pas dans le HTML brut, voir
spider_js.py (variante Playwright) plus bas dans ce fichier.
"""

import os
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = os.environ.get("SCRAPER_USER_AGENT", "SkapaChatbotBot/1.0")
MAX_PAGES = int(os.environ.get("SCRAPER_MAX_PAGES", 100))
DELAY_SECONDS = float(os.environ.get("SCRAPER_DELAY_SECONDS", 0.5))


def _same_domain(base_url, candidate_url):
    return urlparse(base_url).netloc == urlparse(candidate_url).netloc


def crawl(start_url, max_pages=MAX_PAGES):
    """
    Parcourt le site à partir de start_url.
    Retourne une liste de dicts : [{"url": ..., "html": ...}, ...]
    """
    to_visit = [start_url]
    visited = set()
    pages = []

    headers = {"User-Agent": USER_AGENT}

    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"[spider] echec sur {url}: {exc}")
            continue

        pages.append({"url": url, "html": response.text})

        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a", href=True):
            next_url = urljoin(url, link["href"]).split("#")[0]
            if _same_domain(start_url, next_url) and next_url not in visited:
                to_visit.append(next_url)

        time.sleep(DELAY_SECONDS)  # on ne surcharge pas le serveur cible

    print(f"[spider] {len(pages)} pages recuperees depuis {start_url}")
    return pages


def crawl_with_playwright(start_url, max_pages=MAX_PAGES):
    """
    Variante pour les sites qui chargent leur contenu en JavaScript.
    Nécessite : pip install playwright && playwright install chromium
    """
    from playwright.sync_api import sync_playwright

    to_visit = [start_url]
    visited = set()
    pages = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        while to_visit and len(visited) < max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                page.goto(url, timeout=15000, wait_until="networkidle")
            except Exception as exc:
                print(f"[spider-js] echec sur {url}: {exc}")
                continue

            html = page.content()
            pages.append({"url": url, "html": html})

            soup = BeautifulSoup(html, "html.parser")
            for link in soup.find_all("a", href=True):
                next_url = urljoin(url, link["href"]).split("#")[0]
                if _same_domain(start_url, next_url) and next_url not in visited:
                    to_visit.append(next_url)

            time.sleep(DELAY_SECONDS)

        browser.close()

    print(f"[spider-js] {len(pages)} pages recuperees depuis {start_url}")
    return pages


if __name__ == "__main__":
    # Lancement manuel : python -m scraper.spider
    target = os.environ.get("SCRAPER_TARGET_URL", "https://skapa-academy.com")
    crawl(target)
