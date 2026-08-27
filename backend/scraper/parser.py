"""
Parser générique :
  1. clean_html()  -> retire script/style/nav/footer, extrait titre + texte
  2. chunk_text()  -> découpe en blocs pour l'embedding
  3. parse_page()  -> retourne des chunks avec metadata enrichies
"""

import os
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

CHUNK_SIZE = int(os.environ.get("SCRAPER_CHUNK_SIZE", 800))
CHUNK_OVERLAP = int(os.environ.get("SCRAPER_CHUNK_OVERLAP", 100))


def clean_html(html):
    """Transforme une page HTML en texte propre avec structure préservée."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # Préfixe les headings pour conserver la hiérarchie dans le texte
    for level in range(1, 7):
        for h in soup.find_all(f"h{level}"):
            prefix = "#" * level
            h.replace_with(f"\n{prefix} {h.get_text(strip=True)}\n")

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)

    return title, text


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Découpe un texte en morceaux qui se chevauchent légèrement."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return chunks


def parse_page(url, html, depth=0):
    """Retourne des chunks prêts à indexer avec metadata complètes."""
    title, text = clean_html(html)
    source_domain = urlparse(url).netloc
    scraped_at = datetime.now(timezone.utc).isoformat()
    chunks = chunk_text(text)

    return [
        {
            "id": f"{url}#{i}",
            "text": chunk,
            "metadata": {
                "url": url,
                "title": title,
                "source_domain": source_domain,
                "scraped_at": scraped_at,
                "depth": depth,
                "chunk_index": i,
            },
        }
        for i, chunk in enumerate(chunks)
    ]


if __name__ == "__main__":
    import requests

    target = os.environ.get("SCRAPER_TARGET_URL", "https://example.com")
    response = requests.get(target, timeout=15)
    result = parse_page(target, response.text, depth=0)
    print(f"{len(result)} chunks depuis {target}")
    if result:
        print("--- metadata du premier chunk ---")
        print(result[0]["metadata"])
        print("--- debut du texte ---")
        print(result[0]["text"][:300])
