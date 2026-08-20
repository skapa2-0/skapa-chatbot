"""Extrait et nettoie le contenu textuel utile d'une page HTML.

En plus du texte visible, on récupère les données structurées JSON-LD
(`<script type="application/ld+json">`) que la plupart des plateformes
(WordPress, Shopify, PrestaShop, sites e-commerce...) publient pour le SEO :
elles contiennent souvent l'information la plus exploitable de la page
(prix, dates, horaires, auteur, notes) sous une forme déjà propre.
"""
import json

from bs4 import BeautifulSoup

from app.config import Config

# Balises de mise en page, sans contenu informatif pour le chatbot.
_NOISE_TAGS = ["script", "style", "nav", "footer", "header", "noscript", "svg", "form", "aside"]


def html_to_text(html: str) -> str:
    """HTML -> texte lisible, espaces normalisés. Tolère un fragment ou une page entière."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_NOISE_TAGS):
        tag.decompose()

    return " ".join(soup.get_text(separator=" ").split())


def extract_jsonld(soup: BeautifulSoup) -> str:
    """Aplatit les blocs JSON-LD de la page en lignes "clé: valeur"."""
    from app.extractors import flatten

    lines: list[str] = []
    for block in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = block.string or block.get_text() or ""
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        lines.extend(flatten(payload))

    return "\n".join(lines)


def parse_page(url: str, html: str, site_id: str | None = None, source_type: str = "html") -> dict | None:
    """Retourne un document prêt à être indexé, ou None si la page n'a rien d'utile."""
    from app.extractors import make_doc

    site_id = site_id or Config.DEFAULT_SITE_ID
    soup = BeautifulSoup(html, "html.parser")

    # Le JSON-LD est lu avant le nettoyage, puisqu'il vit dans une balise <script>.
    structured = extract_jsonld(soup)

    for tag in soup(_NOISE_TAGS):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else url
    if soup.h1 and soup.h1.get_text(strip=True):
        title = title or soup.h1.get_text(strip=True)

    text = " ".join(soup.get_text(separator=" ").split())
    content = f"{title}\n{text}"
    if structured:
        content = f"{content}\n\nDonnées structurées :\n{structured}"

    return make_doc(site_id, source_type, url, title, content, seed=url)
