"""Choix du moteur de crawling (requests ou Playwright) selon la nature du site."""

import requests
from bs4 import BeautifulSoup

from app import config
from scraper.parser import clean_html
from scraper.spider import USER_AGENT, crawl, crawl_with_playwright

USE_PLAYWRIGHT_MODE = config.env("SCRAPER_USE_PLAYWRIGHT", "auto").lower()
MIN_TEXT_LENGTH = config.env_int("SCRAPER_SPA_MIN_TEXT_LENGTH", 200)
MIN_LINKS_FOUND = config.env_int("SCRAPER_SPA_MIN_LINKS", 1)


def looks_like_js_rendered_spa(html):
    """Peu de texte / pas de liens dans le HTML brut -> contenu généré en JS."""
    _, text = clean_html(html)
    soup = BeautifulSoup(html, "html.parser")
    nb_links = len(soup.find_all("a", href=True))
    app_root = soup.find(id="root") or soup.find(id="__next") or soup.find(id="app") \
        or soup.find(id="__nuxt") or soup.find(attrs={"ng-version": True})
    is_thin = len(text) < MIN_TEXT_LENGTH
    return is_thin or nb_links < MIN_LINKS_FOUND or bool(app_root and nb_links <= 2)


def precheck_is_spa(target_url):
    try:
        resp = requests.get(target_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[pipeline] pre-check échoué ({exc}) -> Playwright")
        return True
    spa = looks_like_js_rendered_spa(resp.text)
    print(f"[pipeline] pre-check {target_url}: {'SPA -> Playwright' if spa else 'HTML statique -> requests'}")
    return spa


def resolve_scheme(target_url):
    """Le spider résout déjà les redirections http<->https.
    Garde cette fonction uniquement pour les SSL errors franches."""
    if not target_url.startswith("https://"):
        return target_url
    try:
        requests.head(target_url, headers={"User-Agent": USER_AGENT},
                      timeout=5, allow_redirects=True)
        return target_url
    except requests.exceptions.SSLError:
        http_url = "http://" + target_url[len("https://"):]
        print(f"[pipeline] SSL error -> {http_url}")
        return http_url
    except requests.RequestException:
        return target_url


def pick_engine_and_crawl(target_url, max_pages, max_depth, progress):
    if USE_PLAYWRIGHT_MODE == "true":
        return crawl_with_playwright(target_url, max_pages, max_depth, progress), "playwright"
    if USE_PLAYWRIGHT_MODE == "false":
        return crawl(target_url, max_pages, max_depth, progress), "requests"

    if precheck_is_spa(target_url):
        try:
            return crawl_with_playwright(target_url, max_pages, max_depth, progress), "playwright"
        except Exception as exc:
            print(f"[pipeline] Playwright indisponible ({exc}) -> requests")
            return crawl(target_url, max_pages, max_depth, progress), "requests"

    result = crawl(target_url, max_pages, max_depth, progress)
    pages = result[0]
    if len(pages) <= 1 and max_pages > 1:
        try:
            js_result = crawl_with_playwright(target_url, max_pages, max_depth, progress)
            if len(js_result[0]) > len(pages):
                return js_result, "playwright"
        except Exception as exc:
            print(f"[pipeline] repli Playwright impossible ({exc})")
    return result, "requests"
