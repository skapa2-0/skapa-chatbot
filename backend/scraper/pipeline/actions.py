"""Extraction des liens CTA (call-to-action) depuis la page d'accueil.

Stratégie :
  1. Cherche dans <header>, <nav>, [role=navigation] ET <footer>
  2. Ne garde que les liens avec INTENTION D'ACTION :
     label ou chemin URL contenant candidat, contact, inscription, rdv…
  3. Score par classe CSS + longueur URL : bouton standalone > lien nav
  4. Déduplication par URL (garde le meilleur score)
  5. Max 3 actions
  6. Pages manquantes récupérées individuellement (requests → Playwright),
     protégées par is_safe_url + même domaine (anti-SSRF)
"""
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from scraper.pipeline.engine_select import looks_like_js_rendered_spa
from scraper.spider.const import REQUEST_TIMEOUT, USER_AGENT
from scraper.spider.safe_url import is_safe_url
from scraper.spider.urls import is_crawlable, normalize_url, same_domain

# Mots-clés qui signalent une intention d'action dans le label ou le chemin URL
_ACTION_INTENT_RE = re.compile(
    r'contact|candidat|cond[io]dat|postuler|inscri|rencontr|rendez.?vous|\brdv\b|'
    r'devis|d[eé]mo|r[eé]serv|apply|signup|sign[\-_ ]?up|book|rejoindre|particip|'
    r'candidature|engag|s.inscri|soumettre|demande',
    re.I,
)

# Classe CSS signalant un bouton CTA "pur" (Webflow, Bootstrap, etc.)
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
})


def _has_action_intent(label: str, url: str) -> bool:
    """True si le libellé OU le chemin URL contient un mot-clé d'action."""
    return bool(
        _ACTION_INTENT_RE.search(label) or
        _ACTION_INTENT_RE.search(urlparse(url).path)
    )


def _cta_score(label: str, url: str, cls: str) -> int:
    """Score de priorité CTA : plus c'est élevé, plus c'est un vrai bouton d'action."""
    score = 0
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split('/') if p]

    if _PURE_BTN_RE.search(cls):
        score += 60
    elif _BTN_RE.search(cls):
        score += 20

    if len(path_parts) == 1:
        score += 25
    elif len(path_parts) >= 3:
        score -= 10
    if not parsed.query:
        score += 10

    if re.search(r'\d', label):
        score -= 30

    words = label.split()
    if len(words) <= 3:
        score += 10
    elif len(words) > 5:
        score -= 5

    return score


def extract_cta_links(html: str, base_url: str) -> list[dict]:
    """Retourne [{label, url}] depuis le header/nav/footer de la page d'accueil.

    Seuls les liens avec INTENTION D'ACTION sont retenus.
    Résultat limité à 3 entrées triées par score décroissant.
    """
    soup = BeautifulSoup(html, 'html.parser')

    zones = (
        soup.find_all('header') +
        soup.find_all('nav') +
        soup.find_all(attrs={'role': 'navigation'}) +
        soup.find_all('footer')
    )
    if not zones:
        body = soup.find('body')
        zones = [body] if body else [soup]

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

            # Filtre principal : intention d'action obligatoire
            if not _has_action_intent(label, full_url):
                continue

            cls = ' '.join(tag.get('class', []))
            score = _cta_score(label, full_url, cls)
            prev = best.get(full_url)
            if prev is None or score > prev['_score']:
                best[full_url] = {'label': label, 'url': full_url, '_score': score}

    candidates = sorted(best.values(), key=lambda x: -x['_score'])
    return [{'label': c['label'], 'url': c['url']} for c in candidates[:3]]


def fetch_missing_cta_pages(cta_links: list[dict], crawled_urls: set,
                             base_url: str) -> list[dict]:
    """Récupère les pages CTA pas encore crawlées.

    Protégé contre le SSRF : is_safe_url() + même domaine que base_url.
    Utilise requests, puis Playwright si le contenu est généré en JS.
    """
    missing = [
        c['url'] for c in cta_links
        if c['url'] not in crawled_urls
        and same_domain(base_url, c['url'])   # même domaine (anti-SSRF niveau 1)
        and is_safe_url(c['url'])             # IP publique (anti-SSRF niveau 2)
    ]
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
            # Vérifie que la redirection éventuelle reste sur le même domaine
            final_url = resp.url
            if not same_domain(base_url, final_url) or not is_safe_url(final_url):
                print(f"[actions] redirection hors-domaine bloquée : {final_url}")
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
