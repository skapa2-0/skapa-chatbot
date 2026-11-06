"""Extraction des liens CTA (call-to-action) depuis la page d'accueil.

Stratégie :
  1. Cherche dans <header>, <nav>, [role=navigation]
  2. Score chaque lien : bouton standalone > lien nav simple
     - URL courte (1 segment, pas de query) : score élevé
     - Label court sans chiffres : score élevé
     - Classe CSS w-button / btn-primary / cta… : bonus fort
  3. Renvoie les 6 meilleurs CTAs
  4. Pour les pages CTA pas encore crawlées, les récupère individuellement
     (requests → Playwright si contenu JS détecté)
"""
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scraper.pipeline.engine_select import looks_like_js_rendered_spa
from scraper.spider.const import REQUEST_TIMEOUT, USER_AGENT
from scraper.spider.urls import is_crawlable, normalize_url, same_domain

# Classe CSS signalant un bouton CTA "pur" (sans composante nav)
_PURE_BTN_RE = re.compile(
    r'\b(?:w-button|btn-primary|btn-cta|cta|call[\-_]?to[\-_]?action)\b', re.I,
)
# Classe signalant n'importe quel bouton ou lien interactif
_BTN_RE = re.compile(
    r'\b(?:btn|button|cta|nav[\-_]?link|header[\-_]?link|action)\b', re.I,
)
_GENERIC_LABELS = frozenset({
    'accueil', 'home', 'menu', 'fr', 'en', 'connexion', 'login', 'se connecter',
    'intranet', 'retour', 'back', 'retourner', 'skip to content', 'aller au contenu',
    'en', 'fr',
})


def _cta_score(label: str, url: str, cls: str) -> int:
    """Score de priorité CTA : plus c'est élevé, plus c'est un vrai bouton d'action."""
    score = 0
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split('/') if p]

    # Bonus fort : classe de bouton "pur" (w-button, btn-primary…)
    if _PURE_BTN_RE.search(cls):
        score += 60
    elif _BTN_RE.search(cls):
        score += 20

    # Bonus : URL courte sans query params (page principale, pas un filtre)
    if len(path_parts) == 1:
        score += 25
    elif len(path_parts) >= 3:
        score -= 10
    if not parsed.query:
        score += 10

    # Pénalité : label contient des chiffres (items de mega-menu concaténés)
    if re.search(r'\d', label):
        score -= 30

    # Bonus : label court (1-3 mots)
    words = label.split()
    if len(words) <= 3:
        score += 10
    elif len(words) > 5:
        score -= 5

    return score


def extract_cta_links(html: str, base_url: str) -> list[dict]:
    """Retourne [{label, url}] depuis le header/nav de la page d'accueil.

    Préfère les liens stylisés en bouton standalone (w-button, btn-primary…),
    pénalise les items de mega-menu (labels avec chiffres, URL profondes).
    Résultat limité à 6 entrées triées par score décroissant.
    """
    soup = BeautifulSoup(html, 'html.parser')

    zones = (
        soup.find_all('header') +
        soup.find_all('nav') +
        soup.find_all(attrs={'role': 'navigation'})
    )
    if not zones:
        body = soup.find('body')
        zones = [body] if body else [soup]

    # url -> meilleur candidat (on garde le score le plus élevé par URL)
    best: dict = {}

    for zone in zones:
        for tag in zone.find_all('a', href=True):
            href = tag['href'].strip()
            if not href or href.startswith(('mailto:', 'tel:', 'javascript:', '#', 'data:')):
                continue
            full_url = normalize_url(urljoin(base_url, href))
            if not same_domain(base_url, full_url) or not is_crawlable(full_url):
                continue
            if urlparse(full_url).path in ('', '/'):
                continue

            label = re.sub(r'\s+', ' ', tag.get_text(separator=' ', strip=True))
            if not label or len(label) > 60 or label.lower() in _GENERIC_LABELS:
                continue

            cls = ' '.join(tag.get('class', []))
            score = _cta_score(label, full_url, cls)
            prev = best.get(full_url)
            if prev is None or score > prev['_score']:
                best[full_url] = {'label': label, 'url': full_url, '_score': score}

    candidates = sorted(best.values(), key=lambda x: -x['_score'])
    return [{'label': c['label'], 'url': c['url']} for c in candidates[:6]]


def fetch_missing_cta_pages(cta_links: list[dict], crawled_urls: set,
                             base_url: str) -> list[dict]:
    """Récupère les pages CTA pas encore crawlées.

    Utilise requests, puis Playwright si le contenu est généré en JS.
    """
    missing = [c['url'] for c in cta_links if c['url'] not in crawled_urls]
    if not missing:
        return []

    pages = []
    for url in missing:
        print(f"[actions] récupération CTA manquante : {url}")
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT},
                                timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if not resp.ok:
                continue
            html = resp.text
            if looks_like_js_rendered_spa(html):
                print(f"[actions] {url} semble JS-rendu, essai Playwright")
                try:
                    from scraper.spider.playwright_engine import crawl_with_playwright
                    pw_pages, _, _ = crawl_with_playwright(url, max_pages=1, max_depth=0)
                    if pw_pages:
                        html = pw_pages[0].get('html', html)
                except Exception as exc:
                    print(f"[actions] Playwright échoué pour {url}: {exc}")
            pages.append({'url': url, 'depth': 1, 'html': html})
        except Exception as exc:
            print(f"[actions] fetch échoué pour {url}: {exc}")
    return pages
