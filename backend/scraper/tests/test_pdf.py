"""Tests unitaires pour l'extraction de texte PDF (PyMuPDF)."""

import pymupdf

from scraper.parser import parse_page
from scraper.parser.pdf import extract_pdf_text, is_pdf


def _make_pdf(text="Bonjour", title="Test") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.set_metadata({"title": title})
    return doc.tobytes()


def test_is_pdf():
    assert is_pdf("https://x.fr/p", "application/pdf")
    assert not is_pdf("https://x.fr/p", "text/html")
    assert is_pdf("https://x.fr/f.PDF", "text/html")
    assert not is_pdf("https://x.fr/p.html", "text/html")

def test_extract_pdf_text_returns_title_and_text():
    title, text = extract_pdf_text(_make_pdf("Bonjour", "MonTitre"), "https://x.fr/d.pdf")
    assert title == "MonTitre" and "Bonjour" in text

def test_corrupted_pdf_returns_empty():
    assert extract_pdf_text(b"not a pdf", "https://x.fr/d.pdf") == ("", "")

def test_parse_page_with_pdf_text_sets_format_pdf():
    chunks = parse_page("https://x.fr/d.pdf", None, text="Contenu", title="MonPDF")
    assert chunks[0]["metadata"]["format"] == "pdf"
    assert chunks[0]["metadata"]["kind"] == "page"


def test_crawl_keeps_pdf_page(monkeypatch):
    from scraper import spider
    pdf_data = _make_pdf("Brochure")
    class Resp:
        def __init__(self, url):
            self.url, is_p = url, url.endswith(".pdf")
            self.headers = {"Content-Type": "application/pdf" if is_p else "text/html"}
            self.content = pdf_data if is_p else b'<a href="/brochure.pdf">PDF</a>'
            self.text = "" if is_p else self.content.decode()
            self.status_code, self.encoding = 200, "utf-8"
        def raise_for_status(self): pass
    class FakeSession:
        headers = {}
        def mount(self, *a): pass
        def get(self, url, **kw): return Resp(url)
    monkeypatch.setattr(spider.requests, "Session", FakeSession)
    monkeypatch.setattr(spider, "Robots",
        lambda u: type("R", (), {"allowed": lambda s, u: True, "sitemaps": []})())
    monkeypatch.setattr(spider, "discover_sitemap_urls", lambda *a, **k: set())
    monkeypatch.setattr(spider, "DELAY_SECONDS", 0)
    pages, _, _ = spider.crawl("https://site.fr", max_pages=10, max_depth=2)
    pdf_pages = [p for p in pages if p.get("format") == "pdf"]
    assert pdf_pages and pdf_pages[0]["url"] == "https://site.fr/brochure.pdf"
