"""
Parser ultra simple :
  1. clean_html()  -> retire script/style/nav/footer, ne garde que le texte
  2. chunk_text()  -> découpe le texte en petits blocs pour l'embedding
"""

import os

from bs4 import BeautifulSoup

CHUNK_SIZE = int(os.environ.get("SCRAPER_CHUNK_SIZE", 800))       # caracteres
CHUNK_OVERLAP = int(os.environ.get("SCRAPER_CHUNK_OVERLAP", 100))  # caracteres


def clean_html(html):
    """Transforme une page HTML brute en texte propre et lisible."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    clean_lines = [line for line in lines if line]  # retire les lignes vides
    text = "\n".join(clean_lines)

    return title, text


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Découpe un texte long en morceaux qui se chevauchent un peu,
    pour ne pas couper une idée en plein milieu."""
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap  # on recule un peu pour garder du contexte

    return chunks


def parse_page(url, html):
    """Prend une page scrapée et retourne une liste de chunks prêts à indexer."""
    title, text = clean_html(html)
    chunks = chunk_text(text)

    return [
        {
            "id": f"{url}#{i}",
            "text": chunk,
            "metadata": {"url": url, "title": title, "chunk_index": i},
        }
        for i, chunk in enumerate(chunks)
    ]


if __name__ == "__main__":
    # Test rapide : python -m scraper.parser
    import requests

    target = os.environ.get("SCRAPER_TARGET_URL", "https://skapa-academy.com")
    response = requests.get(target, timeout=15)
    result = parse_page(target, response.text)
    print(f"{len(result)} chunks generes depuis {target}")
    if result:
        print("--- premier chunk ---")
        print(result[0]["text"][:300])
