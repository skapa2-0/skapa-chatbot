from scraper.parser import clean_html, chunk_text, parse_page

SAMPLE_HTML = """
<html>
  <head><title>Ma page</title></head>
  <body>
    <nav>menu a ignorer</nav>
    <h1>Titre</h1>
    <p>Premier paragraphe utile.</p>
    <script>console.log("a ignorer")</script>
    <footer>pied de page a ignorer</footer>
  </body>
</html>
"""


def test_clean_html_extracts_title_and_text():
    title, text = clean_html(SAMPLE_HTML)
    assert title == "Ma page"
    assert "Premier paragraphe utile." in text
    assert "a ignorer" not in text


def test_chunk_text_respects_size_and_overlap():
    text = "a" * 1000
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    assert all(len(c) <= 300 for c in chunks)
    assert len(chunks) > 1


def test_parse_page_returns_chunks_with_metadata():
    chunks = parse_page("https://example.com", SAMPLE_HTML)
    assert len(chunks) >= 1
    assert chunks[0]["metadata"]["url"] == "https://example.com"
    assert chunks[0]["metadata"]["title"] == "Ma page"
