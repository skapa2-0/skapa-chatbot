"""Tests pour scraper/pipeline/actions.py (sans réseau)."""
from scraper.pipeline.actions import extract_cta_links, _has_action_intent


BASE = "https://exemple.fr"


# ── _has_action_intent ────────────────────────────────────────────────────────

def test_intent_on_label_candidater():
    assert _has_action_intent("Candidater", "https://exemple.fr/page")

def test_intent_on_label_contact():
    assert _has_action_intent("Nous contacter", "https://exemple.fr/page")

def test_intent_on_url_path():
    assert _has_action_intent("Cliquez ici", "https://exemple.fr/candidater")

def test_no_intent_category_label():
    assert not _has_action_intent("Formations", "https://exemple.fr/formations")

def test_intent_typo_condidater():
    assert _has_action_intent("condidater", "https://exemple.fr/page")


# ── extract_cta_links — détection ─────────────────────────────────────────────

def test_detects_button_link_in_header():
    html = '''<html><body>
    <header>
      <a href="/candidater" class="btn btn-primary">Candidater</a>
    </header></body></html>'''
    result = extract_cta_links(html, BASE)
    assert any(r['label'] == 'Candidater' and r['url'].endswith('/candidater')
               for r in result)


def test_detects_action_nav_links():
    html = '''<html><body>
    <nav>
      <a href="/contact">Nous contacter</a>
      <a href="/inscription">S\'inscrire</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    labels = [r['label'] for r in result]
    assert 'Nous contacter' in labels
    assert "S'inscrire" in labels


def test_ignores_category_links():
    """Les pages de catégories (formations, produits) ne sont pas des actions."""
    html = '''<html><body>
    <nav>
      <a href="/formations">Formations</a>
      <a href="/contact">Contact</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    labels = [r['label'] for r in result]
    assert 'Formations' not in labels
    assert 'Contact' in labels


def test_ignores_homepage_link():
    html = '''<html><body>
    <nav>
      <a href="/">Accueil</a>
      <a href="/contact">Contact</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    urls = [r['url'] for r in result]
    assert BASE + '/' not in urls
    assert BASE not in urls
    assert any('/contact' in u for u in urls)


def test_ignores_external_links():
    html = '''<html><body>
    <nav>
      <a href="https://autre-site.fr/candidater">Externe</a>
      <a href="/contact">Contact</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    for r in result:
        assert 'autre-site.fr' not in r['url']
    assert any('/contact' in r['url'] for r in result)


def test_ignores_mailto_and_tel():
    html = '''<html><body>
    <nav>
      <a href="mailto:contact@exemple.fr">Email</a>
      <a href="tel:0123456789">Appel</a>
      <a href="/candidater">Candidater</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    for r in result:
        assert not r['url'].startswith('mailto:')
        assert not r['url'].startswith('tel:')


def test_button_links_ranked_before_nav_links():
    html = '''<html><body>
    <header>
      <nav>
        <a href="/contact-a">Contacter A</a>
        <a href="/contact-b">Contacter B</a>
      </nav>
      <a href="/candidater" class="btn-cta">Candidater</a>
    </header></body></html>'''
    result = extract_cta_links(html, BASE)
    btn = next((r for r in result if r['label'] == 'Candidater'), None)
    assert btn is not None
    if len(result) >= 2:
        assert result[0]['label'] == 'Candidater'


def test_ignores_generic_labels():
    html = '''<html><body>
    <nav>
      <a href="/accueil">Accueil</a>
      <a href="/connexion">Connexion</a>
      <a href="/contact">Contact</a>
    </nav></body></html>'''
    result = extract_cta_links(html, BASE)
    labels_lower = [r['label'].lower() for r in result]
    assert 'accueil' not in labels_lower
    assert 'connexion' not in labels_lower
    assert 'contact' in labels_lower


def test_limits_to_three():
    links = ''.join(f'<a href="/contact-{i}">Contacter {i}</a>' for i in range(10))
    html = f'<html><body><nav>{links}</nav></body></html>'
    result = extract_cta_links(html, BASE)
    assert len(result) <= 3


def test_empty_html_returns_empty():
    assert extract_cta_links('', BASE) == []


def test_no_header_nav_falls_back_to_body():
    html = '''<html><body>
      <a href="/contact" class="btn">Contacter</a>
    </body></html>'''
    result = extract_cta_links(html, BASE)
    assert any('/contact' in r['url'] for r in result)


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


def test_detects_footer_contact_link():
    """Les liens de contact dans le footer sont aussi détectés."""
    html = '''<html><body>
    <header><a href="/formations">Formations</a></header>
    <footer><a href="/contact">Nous contacter</a></footer>
    </body></html>'''
    result = extract_cta_links(html, BASE)
    assert any('/contact' in r['url'] for r in result)
