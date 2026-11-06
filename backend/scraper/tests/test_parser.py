from scraper.parser import (chunk_text, clean_html, extract_site_info, parse_page,
                            prepare_page_text, site_info_chunks)
from scraper.parser.html_clean import boilerplate_lines

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


# ── boilerplate_lines ─────────────────────────────────────────────────────────

def test_boilerplate_lines_detects_repeated_lines():
    """Une ligne présente sur ≥60 % des pages uniques est boilerplate."""
    repeated = "Tagline commune à toutes les pages du site web."
    pages = [f"{repeated}\nContenu unique {i}." for i in range(10)]
    result = boilerplate_lines(pages, min_pages=5, min_ratio=0.6)
    assert repeated in result


def test_boilerplate_lines_ignores_short_labels():
    """Les labels courts (<15 chars) ne sont pas retenus."""
    pages = ["Durée\nFoo bar baz" for _ in range(10)]
    result = boilerplate_lines(pages)
    assert "Durée" not in result


def test_boilerplate_deduplicates_identical_pages():
    """Pages identiques comptent comme une seule pour le calcul du seuil.

    Sans dédup : 10 pages identiques font monter le compteur → faux boilerplate.
    Avec dédup : elles comptent pour 1, le seuil n'est pas atteint."""
    listing_line = "Découvrez les témoignages de nos apprenants et les tendances."
    repeated_page = f"{listing_line}\nAutre contenu du listing."
    unique_pages = [f"Contenu unique et spécifique à la page {i}." for i in range(4)]
    # 10 pages identiques + 4 uniques = 14 pages
    texts = [repeated_page] * 10 + unique_pages
    result = boilerplate_lines(texts, min_pages=5, min_ratio=0.6)
    # Sans dédup, listing_line apparaîtrait sur 10/14 pages → boilerplate
    # Avec dédup, 1 unique listing + 4 uniques = 5 unique texts ; threshold = max(5,3)=5
    # listing_line sur 1/5 pages → pas boilerplate
    assert listing_line not in result, "Ligne d'une page dupliquée ne doit pas être boilerplate"


# ── parse_page safety net ─────────────────────────────────────────────────────

_PAGE_WITH_CONTENT = """
<html>
  <head><title>Formation Développeur Web</title></head>
  <body>
    <main>
      <h1>Formation Développeur Web</h1>
      <p>Apprenez à créer des applications web modernes avec HTML, CSS et JavaScript.</p>
      <p>Durée : 6 mois. Format : présentiel. Financement : CPF.</p>
    </main>
  </body>
</html>
"""


def test_parse_page_fallback_when_strip_lines_would_empty_page():
    """Si strip_lines viderait la page (< 200 chars), on garde le texte original."""
    _, text = prepare_page_text("https://example.com/dev-web", _PAGE_WITH_CONTENT)
    all_lines = {ln.strip() for ln in text.splitlines() if ln.strip()}
    # Marquer TOUTES les lignes comme boilerplate
    chunks = parse_page("https://example.com/dev-web", _PAGE_WITH_CONTENT, strip_lines=all_lines)
    assert len(chunks) >= 1
    full_text = " ".join(c["text"] for c in chunks)
    assert "Formation Développeur Web" in full_text


def test_parse_page_strips_true_boilerplate():
    """Les vraies lignes boilerplate sont retirées quand la page reste lisible."""
    boilerplate = "Cette ligne apparaît sur toutes les pages du site web entier."
    unique = "\n".join(
        f"Paragraphe unique {i} avec du contenu spécifique à cette formation."
        for i in range(10)
    )
    html = f"<html><head><title>Page</title></head><body><p>{boilerplate}</p><p>{unique}</p></body></html>"
    _, text = prepare_page_text("https://example.com/page", html)
    chunks = parse_page("https://example.com/page", html, strip_lines={boilerplate})
    full_text = " ".join(c["text"] for c in chunks)
    assert boilerplate not in full_text
    assert "Paragraphe unique 0" in full_text
