"""Helpers pour l'extraction de couleurs brand depuis du CSS."""
import colorsys
import re

import requests

from scraper.spider.safe_url import is_safe_url
from scraper.spider.urls import same_domain

_HEX_RE = re.compile(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])')
_RGB_RE = re.compile(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', re.I)
_CSS_TIMEOUT = 5
_CSS_MAX_BYTES = 500_000


def _hex_to_hsl(h: str) -> tuple:
    """'#rrggbb' ou '#rgb' → (H 0-1, S 0-1, L 0-1)."""
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
    h_val, l_val, s_val = colorsys.rgb_to_hls(r, g, b)
    return h_val, s_val, l_val


def _is_good_color(c: str) -> bool:
    """True si la couleur est saturée et ni trop sombre ni trop claire."""
    try:
        _, s, l = _hex_to_hsl(c)
        return s >= 0.35 and 0.2 <= l <= 0.75
    except Exception:
        return False


def _normalize(val: str) -> "str | None":
    """Renvoie '#rrggbb' normalisé ou None."""
    val = (val or '').strip()
    m = _HEX_RE.search(val)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        return '#' + h.lower()
    m = _RGB_RE.search(val)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if max(r, g, b) > 255:
            return None
        return '#{:02x}{:02x}{:02x}'.format(r, g, b)
    return None


def _scores_from_css(css: str) -> dict:
    """Retourne {couleur: score} — variables primary/brand/accent/main ont +10, autres +1."""
    scores: dict = {}
    for m in re.finditer(
        r'(--[\w-]*(?:primary|brand|accent|main|color)[\w-]*)\s*:\s*([^;}{]+)', css, re.I
    ):
        c = _normalize(m.group(2))
        if c and _is_good_color(c):
            scores[c] = scores.get(c, 0) + 10
    for m in re.finditer(
        r'(?:^|[;{])\s*(?:background-color|color)\s*:\s*([^;}{]+)', css, re.I
    ):
        c = _normalize(m.group(1))
        if c and _is_good_color(c):
            scores[c] = scores.get(c, 0) + 1
    return scores


def _safe_get(url: str, home_url: str) -> "bytes | None":
    """Télécharge url si elle est sûre et sur le même domaine. Renvoie le contenu ou None."""
    if not is_safe_url(url) or not same_domain(url, home_url):
        return None
    try:
        r = requests.get(url, timeout=_CSS_TIMEOUT, headers={"Accept": "*/*"}, stream=True)
        if not r.ok:
            return None
        content = b""
        for chunk in r.iter_content(8192):
            content += chunk
            if len(content) > _CSS_MAX_BYTES:
                break
        return content
    except Exception:
        return None
