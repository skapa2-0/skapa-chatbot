"""Helpers pour l'extraction de couleurs brand depuis du CSS."""
import colorsys
import re

import requests

from scraper.spider.safe_url import is_safe_url
from scraper.spider.urls import same_domain

_HEX_RE = re.compile(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-fA-F])')
_RGB_RE = re.compile(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', re.I)
_CSS_TIMEOUT = 6
_CSS_MAX_BYTES = 600_000

# Noms de variables CSS signalant une couleur primaire / marque (poids fort)
_HIGH_VAR = re.compile(r'primary|secondary|brand|accent|main|cta|highlight|theme', re.I)
# Noms de variables contenant un nom de couleur explicite (poids moyen)
_MED_VAR = re.compile(
    r'red|rouge|blue|bleu|green|vert|orange|purple|violet|yellow|pink|rose|color|colour', re.I
)
_HIGH_SCORE, _MED_SCORE = 50, 10


def _hex_to_hsl(h: str) -> tuple:
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
        return '#{:02x}{:02x}{:02x}'.format(r, g, b) if max(r, g, b) <= 255 else None
    return None


def _resolve_css_vars(css: str) -> dict:
    """Résout les chaînes var(--x) → couleur hexadécimale. Gère les références circulaires."""
    raw: dict = {}
    for m in re.finditer(r'(--[\w-]+)\s*:\s*([^;}{]+)', css):
        name, val = m.group(1), m.group(2).strip()
        if name not in raw:
            raw[name] = val

    resolved: dict = {}

    def resolve(name: str, seen: frozenset = frozenset()) -> "str | None":
        if name in resolved:
            return resolved[name]
        if name in seen:
            resolved[name] = None
            return None
        val = raw.get(name)
        if not val:
            resolved[name] = None
            return None
        vm = re.match(r'var\(\s*(--[\w-]+)[^)]*\)', val)
        if vm:
            result = resolve(vm.group(1), seen | {name})
            resolved[name] = result
            return result
        c = _normalize(val)
        resolved[name] = c
        return c

    for name in raw:
        resolve(name)
    return {k: v for k, v in resolved.items() if v}


def _scores_from_css(css: str) -> dict:
    """Retourne {couleur: score} — var nommées ont un fort bonus, fréquence = faible."""
    scores: dict = {}
    resolved = _resolve_css_vars(css)

    for var_name, color in resolved.items():
        if not _is_good_color(color):
            continue
        if _HIGH_VAR.search(var_name):
            scores[color] = scores.get(color, 0) + _HIGH_SCORE
        elif _MED_VAR.search(var_name):
            scores[color] = scores.get(color, 0) + _MED_SCORE

    for m in re.finditer(
        r'(?:^|[;{])\s*(?:background(?:-color)?|color|border(?:-color)?|fill)\s*:\s*([^;}{]+)',
        css, re.I,
    ):
        value = m.group(1).strip()
        c = _normalize(value)
        if not c:
            vm = re.match(r'var\(\s*(--[\w-]+)', value)
            if vm:
                c = resolved.get(vm.group(1))
        if c and _is_good_color(c):
            scores[c] = scores.get(c, 0) + 1
    return scores


def _fetch_public(url: str) -> "bytes | None":
    """Télécharge url si l'IP est publique (CDN inclus). Protégé contre SSRF."""
    if not url or not is_safe_url(url):
        return None
    try:
        r = requests.get(url, timeout=_CSS_TIMEOUT,
                         headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
                         stream=True)
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


def _safe_get(url: str, home_url: str) -> "bytes | None":
    """Télécharge url si elle est sûre ET sur le même domaine (manifestes)."""
    if not same_domain(url, home_url):
        return None
    return _fetch_public(url)


def _image_dominant_color(data: bytes) -> "str | None":
    """Couleur dominante saturée d'une image (PNG/JPG/WebP). Nécessite Pillow."""
    try:
        from PIL import Image  # noqa: PLC0415
        import io
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img = img.resize((64, 64), Image.LANCZOS)
        raw = img.tobytes()
        pixels = [(raw[i], raw[i+1], raw[i+2])
                  for i in range(0, len(raw), 4) if raw[i+3] > 128]
        if not pixels:
            return None
        buckets: dict = {}
        for r, g, b in pixels:
            key = '#{:02x}{:02x}{:02x}'.format((r >> 4) << 4, (g >> 4) << 4, (b >> 4) << 4)
            if _is_good_color(key):
                buckets[key] = buckets.get(key, 0) + 1
        if not buckets:
            return None
        best = max(buckets, key=buckets.__getitem__)
        r16, g16, b16 = int(best[1:3], 16), int(best[3:5], 16), int(best[5:7], 16)
        same = [(r, g, b) for r, g, b in pixels
                if abs(r - r16) < 16 and abs(g - g16) < 16 and abs(b - b16) < 16]
        if same:
            avg = tuple(round(sum(x[i] for x in same) / len(same)) for i in range(3))
            return '#{:02x}{:02x}{:02x}'.format(*avg)
        return best
    except Exception:
        return None
