"""Tests pour scraper/pipeline/actions.py (sans réseau)."""
from scraper.pipeline.actions import extract_cta_links


BASE = "https://exemple.fr"


# ── extract_cta_links ──────────────────────────────────────────────────────────

def test_detects_button_link_in_header():
    html = '''<html><body>
    <header>
      <a href="/candidater" class="btn btn-primary">Candidater</a>
    </header></body></html>'''
    result = extract_cta_links(html, BASE)
    assert any(r['label'] == 'Candidater' and r['url'].endswith('/candidater')
               for r in result)


def test_detects_nav_links():
    html = '''<html><body>
    <nav>
      <a href="/formations">Formations</a>
      <a href="/contact">Nous contacter</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    labels = [r['label'] for r in result]
    assert 'Formations' in labels
    assert 'Nous contacter' in labels


def test_ignores_homepage_link():
    html = '''<html><body>
    <nav>
      <a href="/">Accueil</a>
      <a href="/formations">Formations</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    urls = [r['url'] for r in result]
    assert BASE + '/' not in urls
    assert BASE not in urls
    assert any('/formations' in u for u in urls)


def test_ignores_external_links():
    html = '''<html><body>
    <nav>
      <a href="https://autre-site.fr/page">Externe</a>
      <a href="/interne">Interne</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    for r in result:
        assert 'autre-site.fr' not in r['url']
    assert any('/interne' in r['url'] for r in result)


def test_ignores_mailto_and_tel():
    html = '''<html><body>
    <nav>
      <a href="mailto:contact@exemple.fr">Email</a>
      <a href="tel:0123456789">Appel</a>
      <a href="/formations">Formations</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    for r in result:
        assert not r['url'].startswith('mailto:')
        assert not r['url'].startswith('tel:')


def test_button_links_ranked_before_nav_links():
    html = '''<html><body>
    <header>
      <nav>
        <a href="/page-a">Page A</a>
        <a href="/page-b">Page B</a>
      </nav>
      <a href="/candidater" class="btn-cta">Candidater</a>
    </header></body></html>'''
    result = extract_cta_links(html, BASE)
    # Le bouton CTA doit être avant les liens nav
    btn = next((r for r in result if r['label'] == 'Candidater'), None)
    assert btn is not None
    if len(result) >= 2:
        assert result[0]['label'] == 'Candidater'


def test_ignores_generic_labels():
    html = '''<html><body>
    <nav>
      <a href="/accueil">Accueil</a>
      <a href="/connexion">Connexion</a>
      <a href="/formations">Formations</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    labels_lower = [r['label'].lower() for r in result]
    assert 'accueil' not in labels_lower
    assert 'connexion' not in labels_lower
    assert 'formations' in labels_lower


def test_limits_to_six():
    links = ''.join(f'<a href="/p{i}">Page {i}</a>' for i in range(20))
    html = f'<html><body><nav>{links}</nav></body></html>'
    result = extract_cta_links(html, BASE)
    assert len(result) <= 6


def test_empty_html_returns_empty():
    assert extract_cta_links('', BASE) == []


def test_no_header_nav_falls_back_to_body():
    html = '''<html><body>
      <a href="/formations" class="btn">Formations</a>
    </body></html>'''
    result = extract_cta_links(html, BASE)
    assert any('/formations' in r['url'] for r in result)


def test_best_label_wins_for_duplicate_url():
    """Si une URL apparaît d'abord avec un mauvais label (sans classe btn),
    puis avec un meilleur label (classe w-button), c'est le meilleur qui gagne."""
    html = '''<html><body>
    <nav>
      <a href="/candidater" class="nav-link">Voir les sessions</a>
      <a href="/candidater" class="w-button">Candidater</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    assert len(result) == 1
    assert result[0]['label'] == 'Candidater'
