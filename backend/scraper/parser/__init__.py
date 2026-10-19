"""Parser générique : HTML -> chunks prêts à indexer.

Points d'entrée publics :
    clean_html(html, url)                      -> (titre, texte markdown)
    extract_site_info(html)                    -> texte du pied de page / contact
    parse_page(url, html, depth, strip_lines,
               text, title)                    -> chunks d'une page (HTML ou PDF)
    site_info_chunks(url, info_text, site_name)-> chunks du bloc contact
    chunk_text(text)                           -> découpage récursif en chunks
    is_pdf(url, content_type)                  -> bool
    extract_pdf_text(data, url)                -> (titre, texte)
"""

from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scraper.parser.chunks import chunk_id, chunk_text
from scraper.parser.contact import extract_site_info
from scraper.parser.html_clean import boilerplate_lines, clean_html, description_of
from scraper.parser.pdf import extract_pdf_text, is_pdf
from scraper.spider import domain_key


def prepare_page_text(url, html):
    """Texte prêt à chunker : (titre, texte principal + description injectée).
    Exposé pour que le pipeline multi-pages puisse pré-calculer le texte et
    détecter le boilerplate avant appel à parse_page."""
    title, text = clean_html(html, url=url)
    description = description_of(BeautifulSoup(html or "", "html.parser"))
    if description and description[:60] not in text:
        text = f"{description}\n\n{text}" if text else description
    return title, text


def parse_page(url, html, depth=0, strip_lines=None, text=None, title=None):
    """Chunks prêts à indexer pour une page HTML ou un PDF.

    Pour un PDF, passer `text` et `title` directement (html est ignoré).
    `strip_lines` : lignes boilerplate à retirer (HTML uniquement).
    """
    fmt = "html"
    if text is not None:
        # cas PDF : texte déjà extrait, on l'utilise tel quel
        fmt = "pdf"
        title = title or ""
    else:
        title, text = prepare_page_text(url, html)
        if strip_lines:
            text = "\n".join(ln for ln in text.splitlines() if ln.strip() not in strip_lines)

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
                "format": fmt,
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
