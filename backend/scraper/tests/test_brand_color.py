"""Tests pour l'extraction de la couleur de marque."""
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup

from scraper.pipeline.brand_color_css import (
    _hex_to_hsl, _image_dominant_color, _is_good_color, _normalize,
    _resolve_css_vars, _scores_from_css,
)
from scraper.pipeline.brand_color import (
    extract_brand_color, extract_brand_color_safe, _try_meta, _try_svg,
)


# ── _normalize ────────────────────────────────────────────────────────────────

def test_normalize_hex6():
    assert _normalize("#5B3FD4") == "#5b3fd4"

def test_normalize_hex3():
    assert _normalize("#F00") == "#ff0000"

def test_normalize_rgb():
    assert _normalize("rgb(91, 63, 212)") == "#5b3fd4"

def test_normalize_invalid():
    assert _normalize("not-a-color") is None

def test_normalize_none():
    assert _normalize(None) is None


# ── _is_good_color ────────────────────────────────────────────────────────────

def test_good_color_violet():
    assert _is_good_color("#5b3fd4")

def test_bad_color_white():
    assert not _is_good_color("#ffffff")

def test_bad_color_black():
    assert not _is_good_color("#000000")

def test_bad_color_grey():
    assert not _is_good_color("#888888")

def test_bad_color_too_light():
    assert not _is_good_color("#f0eeff")

def test_bad_color_too_dark():
    assert not _is_good_color("#1a0a3d")


# ── _resolve_css_vars ─────────────────────────────────────────────────────────

def test_resolve_direct_color():
    r = _resolve_css_vars(":root { --primary: #5b3fd4; }")
    assert r.get("--primary") == "#5b3fd4"

def test_resolve_single_hop():
    css = ":root { --primary: var(--brand); --brand: #e53e3e; }"
    r = _resolve_css_vars(css)
    assert r.get("--primary") == "#e53e3e"
    assert r.get("--brand") == "#e53e3e"

def test_resolve_chain():
    css = "--a: var(--b); --b: var(--c); --c: #2b6cb0;"
    r = _resolve_css_vars(css)
    assert r.get("--a") == "#2b6cb0"
    assert r.get("--b") == "#2b6cb0"

def test_resolve_circular_no_hang():
    css = "--a: var(--b); --b: var(--a);"
    r = _resolve_css_vars(css)
    assert r.get("--a") is None or r.get("--b") is None

def test_resolve_ignores_unresolvable():
    css = "--x: var(--unknown);"
    r = _resolve_css_vars(css)
    assert "--x" not in r


# ── _scores_from_css ──────────────────────────────────────────────────────────

def test_scores_high_primary_variable():
    css = ":root { --primary: #e53e3e; }"
    s = _scores_from_css(css)
    assert s.get("#e53e3e", 0) >= 50

def test_scores_med_color_name_variable():
    css = ":root { --btoc-red: #ce0033; }"
    s = _scores_from_css(css)
    assert 10 <= s.get("#ce0033", 0) < 50

def test_scores_frequency_plain_property():
    css = "a { color: #e53e3e; } b { color: #e53e3e; }"
    s = _scores_from_css(css)
    assert s.get("#e53e3e", 0) == 2  # 2 occurrences, freq only

def test_scores_resolves_var_in_property():
    css = ":root { --primary: #2b6cb0; } .btn { background-color: var(--primary); }"
    s = _scores_from_css(css)
    # --primary → HIGH +50, background-color var resolution → +1 → total >= 51
    assert s.get("#2b6cb0", 0) >= 51

def test_scores_primary_beats_frequency():
    # --primary with 1 occurrence should beat a color with 20 frequency occurrences
    primary = "#2b6cb0"
    frequent = "#e53e3e"
    css = f":root {{ --primary: {primary}; }}\n" + (f"a {{ color: {frequent}; }}\n" * 20)
    s = _scores_from_css(css)
    assert s.get(primary, 0) > s.get(frequent, 0)


# ── _try_meta ─────────────────────────────────────────────────────────────────

def test_try_meta_theme_color():
    html = '<html><head><meta name="theme-color" content="#e53e3e"></head></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _try_meta(soup, "https://exemple.fr") == "#e53e3e"

def test_try_meta_ignores_grey():
    html = '<html><head><meta name="theme-color" content="#888888"></head></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _try_meta(soup, "https://exemple.fr") is None


# ── _try_svg ──────────────────────────────────────────────────────────────────

def test_try_svg_in_header():
    html = '<html><body><header><svg><path fill="#e53e3e"/></svg></header></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _try_svg(soup) == "#e53e3e"

def test_try_svg_ignores_black():
    html = '<html><body><header><svg><path fill="#000000"/></svg></header></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _try_svg(soup) is None


# ── extract_brand_color ───────────────────────────────────────────────────────

def test_extract_prefers_meta_over_css():
    html = (
        '<html><head>'
        '<meta name="theme-color" content="#e53e3e">'
        '<style>:root { --primary: #2b6cb0; }</style>'
        '</head></html>'
    )
    assert extract_brand_color("https://exemple.fr", html) == "#e53e3e"

def test_extract_falls_back_to_css():
    html = '<html><head><style>:root { --primary: #2b6cb0; }</style></head></html>'
    assert extract_brand_color("https://exemple.fr", html) == "#2b6cb0"

def test_extract_returns_none_when_no_color():
    html = '<html><head><title>Vide</title></head><body><p>Texte</p></body></html>'
    assert extract_brand_color("https://exemple.fr", html) is None

def test_extract_resolves_var_chain_in_css():
    html = (
        '<html><head><style>'
        '--primary: var(--brand-color); --brand-color: #e53e3e;'
        '</style></head></html>'
    )
    result = extract_brand_color("https://exemple.fr", html)
    assert result == "#e53e3e"


# ── _image_dominant_color ─────────────────────────────────────────────────────

def test_image_dominant_color_returns_none_on_bad_data():
    assert _image_dominant_color(b"not an image") is None

def test_image_dominant_color_with_png():
    try:
        from PIL import Image
        import io
        img = Image.new("RGBA", (10, 10), (229, 0, 43, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        c = _image_dominant_color(buf.getvalue())
        assert c is not None
        # Vérifier que c'est une couleur rouge (#e5XXXX)
        assert c.startswith("#e") or c.startswith("#d") or c.startswith("#f")
    except ImportError:
        pass  # Pillow non installé → skip


# ── extract_brand_color_safe ──────────────────────────────────────────────────

def test_safe_returns_none_on_no_home_page():
    pages = [{"url": "https://exemple.fr/about", "depth": 1, "html": "<p>About</p>"}]
    assert extract_brand_color_safe(pages) is None

def test_safe_never_raises_on_bad_input():
    result = extract_brand_color_safe([{"depth": 0, "html": "<!"}])
    assert result is None or isinstance(result, str)

def test_safe_extracts_from_home():
    pages = [
        {"url": "https://exemple.fr/", "depth": 0,
         "html": '<meta name="theme-color" content="#e53e3e">'}
    ]
    assert extract_brand_color_safe(pages) == "#e53e3e"
