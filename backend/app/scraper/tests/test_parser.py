from scraper.parser import (chunk_text, clean_html, extract_site_info, parse_page,
                            site_info_chunks)

SAMPLE_HTML = """
<html>
  <head><title>Ma page</title><meta name="description" content="Résumé de la page"></head>
  <body>
    <nav>menu a ignorer</nav>
    <div class="cookie-banner">Nous utilisons des cookies</div>
    <h1>Titre</h1>
    <p>Premier paragraphe utile.</p>
    <table><tr><th>Formation</th><th>Prix</th></tr><tr><td>Python</td><td>4 900 €</td></tr></table>
    <script>console.log("a ignorer")</script>
    <footer>12 rue des Lilas, 75011 Paris – Tél : 01 23 45 67 89</footer>
  </body>
</html>
"""


def test_clean_html_extracts_title_and_text():
    title, text = clean_html(SAMPLE_HTML)
    assert title == "Ma page"
    assert "Premier paragraphe utile." in text
    assert "a ignorer" not in text
    assert "cookies" not in text
    assert "rue des Lilas" not in text  # le footer n'est pas dans le texte principal


def test_tables_keep_rows_together():
    _, text = clean_html(SAMPLE_HTML)
    assert "Python | 4 900 €" in text


def test_footer_contact_is_extracted_separately():
    info = extract_site_info(SAMPLE_HTML)
    assert "12 rue des Lilas" in info
    chunks = site_info_chunks("https://www.exemple.com/", info, "Exemple")
    assert chunks and chunks[0]["metadata"]["kind"] == "site_info"
    assert chunks[0]["metadata"]["source_domain"] == "exemple.com"


def test_chunk_text_respects_size_and_overlap():
    text = "a" * 1000
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    assert all(len(c) <= 300 for c in chunks)
    assert len(chunks) > 1


def test_chunk_text_does_not_cut_words():
    text = " ".join(f"mot{i}" for i in range(400))
    chunks = chunk_text(text, chunk_size=200, overlap=40)
    words = set(text.split())
    for c in chunks:
        assert len(c) <= 200
        for w in c.split():
            assert w in words, f"mot coupé : {w}"


def test_chunking_preserves_headings():
    text = "# Formations\nIntro\n\n## Prompt Engineering\nProgramme A\n\n## UX Research\nProgramme B"
    chunks = chunk_text(text, chunk_size=40, overlap=0)
    assert any("## Prompt Engineering" in c for c in chunks)
    assert any("## UX Research" in c for c in chunks)


def test_parse_page_returns_chunks_with_metadata():
    chunks = parse_page("https://www.example.com/page", SAMPLE_HTML)
    assert len(chunks) >= 1
    meta = chunks[0]["metadata"]
    assert meta["url"] == "https://www.example.com/page"
    assert meta["title"] == "Ma page"
    assert meta["source_domain"] == "example.com"  # « www. » ignoré
    assert chunks[0]["text"].startswith("Page : Ma page")
    assert "Résumé de la page" in chunks[0]["text"]
    assert len({c["id"] for c in chunks}) == len(chunks)
