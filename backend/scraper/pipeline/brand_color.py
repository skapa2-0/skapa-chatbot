"""Extraction de la couleur principale de marque depuis la page d'accueil."""
import json
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.pipeline.brand_color_css import (
    _is_good_color, _normalize, _safe_get, _scores_from_css,
)

_MAX_CSS_FILES = 3


def _try_meta(soup: BeautifulSoup, home_url: str) -> "str | None":
    """Cherche theme-color, msapplication-TileColor, mask-icon, manifest."""
    for attrs, attr in [
        ({"name": "theme-color"}, "content"),
        ({"name": "msapplication-TileColor"}, "content"),
    ]:
        tag = soup.find("meta", attrs=attrs)
        if tag:
            c = _normalize(tag.get(attr, ""))
            if c and _is_good_color(c):
                return c

    link = soup.find("link", rel=lambda r: r and "mask-icon" in r)
    if link:
        c = _normalize(link.get("color", ""))
        if c and _is_good_color(c):
            return c

    manifest = soup.find("link", rel=lambda r: r and "manifest" in r)
    if manifest:
        murl = urljoin(home_url, manifest.get("href", ""))
        raw = _safe_get(murl, home_url)
        if raw:
            try:
                data = json.loads(raw)
                c = _normalize(data.get("theme_color", ""))
                if c and _is_good_color(c):
                    return c
            except Exception:
                pass
    return None


def _try_css(soup: BeautifulSoup, home_url: str) -> "str | None":
    """Styles inline + fichiers CSS liés (jusqu'à _MAX_CSS_FILES)."""
    scores: dict = {}

    for tag in soup.find_all("style"):
        for c, s in _scores_from_css(tag.get_text()).items():
            scores[c] = scores.get(c, 0) + s

    fetched = 0
    for tag in soup.find_all("link", rel=lambda r: r and "stylesheet" in r):
        if fetched >= _MAX_CSS_FILES:
            break
        href = tag.get("href", "")
        if not href:
            continue
        url = urljoin(home_url, href)
        raw = _safe_get(url, home_url)
        if raw:
            for c, s in _scores_from_css(raw.decode("utf-8", errors="ignore")).items():
                scores[c] = scores.get(c, 0) + s
            fetched += 1

    return max(scores, key=scores.__getitem__) if scores else None


def _try_svg(soup: BeautifulSoup) -> "str | None":
    """SVG inline dans header/nav/logo : couleur de remplissage."""
    for container in (soup.find("header"), soup.find("nav"), soup):
        if not container:
            continue
        for tag in container.find_all(True):
            fill = tag.get("fill", "")
            c = _normalize(fill)
            if c and _is_good_color(c):
                return c
    return None


def extract_brand_color(home_url: str, home_html: str) -> "str | None":
    """Retourne '#rrggbb' ou None."""
    soup = BeautifulSoup(home_html, "html.parser")
    return _try_meta(soup, home_url) or _try_css(soup, home_url) or _try_svg(soup)


def extract_brand_color_safe(pages: list) -> "str | None":
    """Enveloppe pour le pipeline : ne lève jamais d'exception."""
    try:
        home = next((p for p in pages if p.get("depth") == 0 and "html" in p), None)
        if not home:
            return None
        return extract_brand_color(home["url"], home["html"])
    except Exception as exc:
        print(f"[brand_color] erreur ignorée : {exc}")
        return None
