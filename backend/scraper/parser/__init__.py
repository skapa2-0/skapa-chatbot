"""Parser générique : HTML -> chunks prêts à indexer.

Points d'entrée publics :
    clean_html(html, url)   -> (titre, texte markdown)
    extract_site_info(html) -> texte du pied de page / contact
    parse_page(url, html)   -> chunks d'une page
    site_info_chunks(url, info_text, site_name) -> chunks du bloc contact
    chunk_text(text)        -> découpage récursif en chunks
"""

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scraper.parser.chunks import chunk_id, chunk_text
from scraper.parser.contact import extract_site_info
from scraper.parser.html_clean import clean_html, description_of
from scraper.spider import domain_key


def parse_page(url, html, depth=0):
    """Chunks prêts à indexer. Chaque chunk commence par le titre de la page :
    l'embedding « sait » de quelle page il vient, ce qui améliore la recherche."""
    title, text = clean_html(html, url=url)
    description = description_of(BeautifulSoup(html or "", "html.parser"))
    if description and description[:60] not in text:
        text = f"{description}\n\n{text}" if text else description

    source_domain = domain_key(url)
    scraped_at = datetime.now(timezone.utc).isoformat()
    header = f"Page : {title}\n" if title else ""

    return [
        {
            "id": chunk_id(url, i),
            "text": f"{header}{chunk}",
            "metadata": {
                "url": url,
                "title": title,
                "source_domain": source_domain,
                "scraped_at": scraped_at,
                "depth": depth,
                "chunk_index": i,
                "kind": "page",
            },
        }
        for i, chunk in enumerate(chunk_text(text))
    ]


def site_info_chunks(url, info_text, site_name=""):
    """Chunks « informations de contact » du site (issus du footer)."""
    if not info_text:
        return []
    domain = domain_key(url)
    scraped_at = datetime.now(timezone.utc).isoformat()
    header = f"Informations de contact et coordonnées{(' – ' + site_name) if site_name else ''}\n"
    return [
        {
            "id": chunk_id(f"site-info:{domain}", i),
            "text": header + chunk,
            "metadata": {
                "url": url,
                "title": "Coordonnées / contact",
                "source_domain": domain,
                "scraped_at": scraped_at,
                "depth": 0,
                "chunk_index": i,
                "kind": "site_info",
            },
        }
        for i, chunk in enumerate(chunk_text(info_text))
    ]
