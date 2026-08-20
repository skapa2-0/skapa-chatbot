"""Ingestion universelle : une seule porte d'entrée pour n'importe quelle source.

    ingest("https://un-site-quelconque.com")   -> crawl HTML (ou rendu JS si SPA)
    ingest("https://api.exemple.com/v1/items") -> API JSON
    ingest("https://boutique.com")             -> détecté Shopify -> /products.json
    ingest("https://blog.com")                 -> détecté WordPress -> /wp-json
    ingest("https://site.com/sitemap.xml")     -> toutes les pages du sitemap
    ingest("./export.csv")                      -> une ligne = un document
    ingest("supabase://")                       -> tables SUPABASE_TABLES

`detect()` identifie le type, l'extracteur correspondant produit des
documents normalisés, et `upsert_documents()` les indexe dans Chroma. Le
reste du pipeline RAG (chunking, recherche, génération Claude) est
identique quelle que soit la plateforme d'origine.
"""
import requests

from . import extractors
from . import source_detector as sd
from .config import Config
from .ingestion import upsert_documents


def _has_sitemap(url: str) -> str | None:
    """Un sitemap donne la liste exhaustive des pages : à préférer au crawl de liens."""
    from urllib.parse import urlparse

    parts = urlparse(url)
    for path in ("/sitemap.xml", "/sitemap_index.xml"):
        candidate = f"{parts.scheme}://{parts.netloc}{path}"
        try:
            response = requests.get(
                candidate,
                headers={"User-Agent": Config.SCRAPER_USER_AGENT},
                timeout=Config.INGEST_TIMEOUT,
            )
            if response.ok and "<loc" in response.text[:5000]:
                return candidate
        except requests.RequestException:
            continue
    return None


def extract(detection: dict, site_id: str, max_pages: int | None = None) -> list[dict]:
    """Aiguille vers le bon extracteur selon le type détecté."""
    kind = detection["kind"]
    target = detection["target"]

    # --- Bases de données / plateformes avec API dédiée ---
    if kind == sd.SUPABASE:
        from .supabase_source import fetch_supabase_documents

        table = target.removeprefix("supabase://").strip("/") or None
        return fetch_supabase_documents(site_id=site_id, only_table=table)

    if kind == sd.WORDPRESS:
        return extractors.from_wordpress(target, site_id, max_pages)

    if kind == sd.SHOPIFY:
        return extractors.from_shopify(target, site_id, max_pages)

    # --- Formats structurés ---
    if kind == sd.JSON:
        return extractors.from_json(target, site_id)

    if kind == sd.CSV:
        return extractors.from_csv(target, site_id)

    if kind == sd.PDF:
        return extractors.from_pdf(target, site_id)

    if kind == sd.TEXT:
        return extractors.from_text(target, site_id)

    if kind == sd.SITEMAP:
        return extractors.from_sitemap(target, site_id, max_pages=max_pages)

    if kind == sd.FEED:
        return extractors.from_feed(target, site_id)

    # --- Site web : sitemap si disponible, sinon crawl (avec rendu JS si SPA) ---
    if kind in (sd.HTML, sd.HTML_JS):
        from scraper.spider import fetch_one

        if Config.SCRAPER_PREFER_SITEMAP:
            sitemap_url = _has_sitemap(target)
            if sitemap_url:
                documents = extractors.from_sitemap(sitemap_url, site_id, max_pages=max_pages)
                if documents:
                    return documents
                # Sitemap vide ou illisible : on retombe sur le crawl classique.

        render = kind == sd.HTML_JS
        if not render:
            first_page = fetch_one(target)
            render = bool(first_page) and sd.needs_javascript(first_page)

        return extractors.from_html(target, site_id, render=render, max_pages=max_pages)

    return []


def ingest(target: str = "", site_id: str | None = None, max_pages: int | None = None) -> dict:
    """Détecte, extrait et indexe. Retourne un rapport JSON-sérialisable."""
    site_id = site_id or Config.DEFAULT_SITE_ID
    detection = detect_only(target)

    if detection["kind"] == sd.UNKNOWN:
        return {
            "ok": False,
            "source_type": sd.UNKNOWN,
            "target": detection["target"],
            "reason": detection["reason"],
            "documents": 0,
            "created": 0,
            "updated": 0,
        }

    documents = extract(detection, site_id, max_pages)

    # Un même document peut ressortir deux fois (une URL atteinte par deux
    # chemins) : on dédoublonne avant l'upsert pour éviter un conflit d'unicité.
    unique: dict[str, dict] = {}
    for document in documents:
        unique[document["external_id"]] = document

    created, updated = upsert_documents(list(unique.values()))

    return {
        "ok": True,
        "source_type": detection["kind"],
        "target": detection["target"],
        "detected_by": detection["reason"],
        "site_id": site_id,
        "documents": len(unique),
        "created": created,
        "updated": updated,
    }


def detect_only(target: str = "") -> dict:
    """Expose la détection sans rien indexer (utile pour tester une cible)."""
    return sd.detect(target)
