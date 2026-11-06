"""Tests de protection SSRF : is_safe_url, redirections, sitemaps."""

import pytest
from unittest.mock import MagicMock, patch

import requests as _requests

from scraper.spider.safe_url import is_safe_url


def _dns(ip):
    """Retourne un résultat getaddrinfo minimal pour l'IP donnée."""
    return [(2, 1, 6, "", (ip, 0))]


# ── is_safe_url ───────────────────────────────────────────────────────────────

def test_rejects_link_local_metadata():
    """169.254.169.254 (métadonnées cloud OVH/AWS) doit être refusé."""
    with patch("scraper.spider.safe_url.socket.getaddrinfo", return_value=_dns("169.254.169.254")):
        assert not is_safe_url("http://metadata.internal/latest/")


def test_rejects_loopback():
    """127.0.0.1 est loopback, doit être refusé."""
    assert not is_safe_url("http://127.0.0.1/secret")


def test_rejects_private_range():
    """192.168.x.x est un réseau privé, doit être refusé."""
    with patch("scraper.spider.safe_url.socket.getaddrinfo", return_value=_dns("192.168.1.1")):
        assert not is_safe_url("http://intranet.local/")


def test_rejects_non_http_scheme():
    """Les schémas autres que http/https sont refusés sans résolution DNS."""
    assert not is_safe_url("ftp://example.com/")
    assert not is_safe_url("file:///etc/passwd")
    assert not is_safe_url("gopher://example.com/")


def test_accepts_public_ip():
    """Une IP publique valide doit passer."""
    with patch("scraper.spider.safe_url.socket.getaddrinfo", return_value=_dns("93.184.216.34")):
        assert is_safe_url("https://example.com/page")


def test_rejects_direct_link_local_ip():
    """169.254.169.254 passé en IP directe (sans résolution DNS) doit être refusé."""
    assert not is_safe_url("http://169.254.169.254/latest/meta-data/")


# ── Sitemap index SSRF ────────────────────────────────────────────────────────

def test_sitemap_index_internal_url_not_fetched():
    """Un sitemap index pointant vers 169.254.169.254 ne doit pas être appelé."""
    from scraper.spider.robots import discover_sitemap_urls

    index_xml = (
        b'<?xml version="1.0"?>'
        b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b'<sitemap><loc>http://169.254.169.254/sitemap-secret.xml</loc></sitemap>'
        b'<sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>'
        b'</sitemapindex>'
    )
    pages_xml = (
        b'<?xml version="1.0"?>'
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b'<url><loc>https://example.com/page1</loc></url>'
        b'</urlset>'
    )
    call_log = []

    def mock_get(url, **kwargs):
        if "169.254" in url:
            raise AssertionError(f"URL interne appelée ! : {url}")
        call_log.append(url)
        m = MagicMock()
        m.ok = True
        m.content = index_xml if "sitemap.xml" in url else pages_xml
        return m

    with patch("scraper.spider.robots.requests.get", side_effect=mock_get):
        with patch("scraper.spider.safe_url.socket.getaddrinfo",
                   return_value=_dns("93.184.216.34")):
            discover_sitemap_urls("https://example.com/")

    assert all("169.254" not in u for u in call_log)


# ── Redirection SSRF ──────────────────────────────────────────────────────────

def test_redirect_to_internal_blocked():
    """Une redirection HTTP vers 127.0.0.1 doit lever une ValueError."""
    from scraper.spider.http_utils import fetch, make_session

    def mock_get(url, **kwargs):
        m = MagicMock(spec=_requests.Response)
        m.status_code = 302
        m.is_redirect = True
        m.headers = {"Location": "http://127.0.0.1/secret"}
        return m

    session = make_session()
    with patch.object(session, "get", side_effect=mock_get):
        with patch("scraper.spider.safe_url.socket.getaddrinfo",
                   return_value=_dns("93.184.216.34")):
            with pytest.raises((ValueError, _requests.RequestException)):
                fetch(session, "http://safe.example.com/page")


def test_public_url_passes_fetch():
    """Une URL publique normale est téléchargée sans erreur."""
    from scraper.spider.http_utils import fetch, make_session

    def mock_get_ok(url, **kwargs):
        m = MagicMock(spec=_requests.Response)
        m.status_code = 200
        m.is_redirect = False
        m.headers = {"Content-Type": "text/html"}
        m.encoding = "utf-8"
        m.apparent_encoding = "utf-8"
        m.raise_for_status = MagicMock()
        return m

    session = make_session()
    with patch.object(session, "get", side_effect=mock_get_ok):
        with patch("scraper.spider.safe_url.socket.getaddrinfo",
                   return_value=_dns("93.184.216.34")):
            resp = fetch(session, "http://example.com/page")

    assert resp.status_code == 200
