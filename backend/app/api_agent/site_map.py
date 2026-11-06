"""Plan du site (titre + URL des pages indexées) donné au LLM comme contexte.

Permet de répondre aux questions « quelles sont les formations / services... »
même quand la recherche par similarité ne ramène que quelques pages.
"""

import re
import time
from urllib.parse import urlparse

from app.chroma_client import get_collection

LEGAL_RE = re.compile(
    r"/(mentions?|cgu|cgv|cookies?|confidentialit|privacy|politique|legal|terms|rgpd)", re.I)
MAX_PAGES = 40
_TTL = 60
_cache = {}


def is_legal(url):
    return bool(LEGAL_RE.search(urlparse(url or "").path or ""))


def is_home(url):
    return (urlparse(url or "").path or "/") in ("", "/")


def norm_url(url):
    """Comparaison tolérante : sans « / » final, sans fragment."""
    return (url or "").split("#")[0].rstrip("/")


def site_map(domain, limit=MAX_PAGES):
    """[{title, url}] des pages du domaine (hors pages légales), accueil d'abord."""
    if not domain:
        return []
    cached = _cache.get(domain)
    if cached and time.time() - cached[0] < _TTL:
        return cached[1][:limit]
    res = get_collection().get(where={"source_domain": domain}, include=["metadatas"])
    pages = {}
    for m in res.get("metadatas") or []:
        url = (m or {}).get("url")
        if not url or m.get("kind", "page") != "page" or is_legal(url) or url in pages:
            continue
        pages[url] = (m.get("depth", 9), m.get("title") or url)
    ordered = sorted(pages.items(), key=lambda kv: (kv[1][0], kv[0]))
    out = [{"url": u, "title": t} for u, (_, t) in ordered]
    _cache[domain] = (time.time(), out)
    return out[:limit]


def format_site_map(pages):
    if not pages:
        return ""
    lines = "\n".join(f"- {p['title']} : {p['url']}" for p in pages)
    return f"PLAN DU SITE (pages disponibles, titre : lien) :\n{lines}"


def reset_cache():
    _cache.clear()
