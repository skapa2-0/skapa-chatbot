from scraper.parser import clean_html, chunk_text, parse_page
from scraper import spider


def test_parser_keeps_header_and_navigation_content():
    html = """
    <html><head><title>Catalogue</title></head><body>
      <header>Nom du site</header>
      <nav><a href='/formations'>Nos formations</a></nav>
      <main><h1>Formations</h1><h2>Prompt Engineering</h2><p>Programme complet.</p></main>
      <footer>Contact</footer>
      <script>alert('x')</script>
    </body></html>
    """
    title, text = clean_html(html)
    assert title == "Catalogue"
    assert "Nom du site" not in text
    assert "Nos formations" not in text
    assert "# Formations" in text
    assert "## Prompt Engineering" in text
    assert "alert" not in text
    assert "Contact" not in text


def test_chunking_preserves_headings():
    text = "# Formations\nIntro\n## Prompt Engineering\nProgramme A\n## UX Research\nProgramme B"
    chunks = chunk_text(text, chunk_size=80, overlap=0)
    assert any("## Prompt Engineering" in c for c in chunks)
    assert any("## UX Research" in c for c in chunks)


def test_auto_crawler_falls_back_to_playwright(monkeypatch):
    start = "https://example.com/"
    shell = '<html><body><div id="root"></div><script src="app.js"></script></body></html>'
    rendered = '<html><body><div id="root"><a href="/formation/prompt-engineering">Prompt</a></div></body></html>'

    monkeypatch.setattr(spider, "crawl", lambda *a, **k: (
        [{"url": start.rstrip('/'), "html": shell, "depth": 0}], 0, 0
    ))
    monkeypatch.setattr(spider, "crawl_with_playwright", lambda *a, **k: (
        [{"url": start.rstrip('/'), "html": rendered, "depth": 0}], 0, 1
    ))

    pages, failed, found = spider.crawl_auto(start, max_pages=10, max_depth=2)
    assert pages[0]["html"] == rendered
    assert found == 1
