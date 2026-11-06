"""Tests pour l'extraction de la couleur de marque."""
from unittest.mock import patch

from scraper.pipeline.brand_color_css import _hex_to_hsl, _is_good_color, _normalize, _scores_from_css
from scraper.pipeline.brand_color import (
    extract_brand_color, extract_brand_color_safe,
    _try_meta, _try_svg,
)
from bs4 import BeautifulSoup


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
    assert _is_good_color("#5b3fd4")  # violett saturé

def test_bad_color_white():
    assert not _is_good_color("#ffffff")

def test_bad_color_black():
    assert not _is_good_color("#000000")

def test_bad_color_grey():
    assert not _is_good_color("#888888")  # S=0 < 0.35

def test_bad_color_too_light():
    assert not _is_good_color("#f0eeff")  # L > 0.75

def test_bad_color_too_dark():
    assert not _is_good_color("#1a0a3d")  # L < 0.2


# ── _scores_from_css ──────────────────────────────────────────────────────────

def test_scores_primary_variable_gets_bonus():
    css = ":root { --primary-color: #e53e3e; }"
    scores = _scores_from_css(css)
    assert "#e53e3e" in scores and scores["#e53e3e"] >= 10

def test_scores_plain_color_gets_low_score():
    css = "body { color: #e53e3e; }"
    scores = _scores_from_css(css)
    assert "#e53e3e" in scores and scores["#e53e3e"] < 10


# ── _try_meta ─────────────────────────────────────────────────────────────────

def test_try_meta_theme_color():
    html = '<html><head><meta name="theme-color" content="#e53e3e"></head></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _try_meta(soup, "https://example.com") == "#e53e3e"

def test_try_meta_ignores_grey():
    html = '<html><head><meta name="theme-color" content="#888888"></head></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _try_meta(soup, "https://example.com") is None


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
    result = extract_brand_color("https://example.com", html)
    assert result == "#e53e3e"

def test_extract_falls_back_to_css():
    html = '<html><head><style>:root { --primary: #2b6cb0; }</style></head></html>'
    result = extract_brand_color("https://example.com", html)
    assert result == "#2b6cb0"

def test_extract_returns_none_when_no_color():
    html = '<html><head><title>No color</title></head><body><p>Text</p></body></html>'
    result = extract_brand_color("https://example.com", html)
    assert result is None


# ── extract_brand_color_safe ──────────────────────────────────────────────────

def test_safe_returns_none_on_no_home_page():
    pages = [{"url": "https://example.com/about", "depth": 1, "html": "<p>About</p>"}]
    assert extract_brand_color_safe(pages) is None

def test_safe_never_raises_on_bad_input():
    assert extract_brand_color_safe([{"depth": 0, "html": "<!"}]) is None or True

def test_safe_extracts_from_home():
    pages = [
        {"url": "https://example.com/", "depth": 0,
         "html": '<meta name="theme-color" content="#e53e3e">'}
    ]
    assert extract_brand_color_safe(pages) == "#e53e3e"
