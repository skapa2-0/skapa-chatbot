from flask import Blueprint, jsonify, request
from sqlalchemy import func

from .api_agent import answer
from .config import Config
from .ingestion import upsert_documents
from .models import ChatLog, Document, db
from .supabase_source import fetch_supabase_documents
from .universal_ingest import detect_only, ingest
from .vectorstore import stats
from scraper.parser import parse_page
from scraper.spider import fetch_pages

bp = Blueprint("api", __name__, url_prefix="/api")


def _authorized() -> bool:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return bool(Config.ADMIN_TOKEN) and token == Config.ADMIN_TOKEN


@bp.get("/health")
def health():
    """État de l'API + inventaire de ce qui est indexé, par type de source et par site."""
    by_type = dict(db.session.query(Document.source_type, func.count(Document.id)).group_by(Document.source_type))
    by_site = dict(db.session.query(Document.site_id, func.count(Document.id)).group_by(Document.site_id))

    return jsonify(
        {
            "status": "ok",
            "documents_indexed": Document.query.count(),
            "chunks_indexed": stats()["chunks"],
            "by_source_type": by_type,
            "by_site": by_site,
        }
    )


@bp.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    site_id = data.get("site_id")

    if not question:
        return jsonify({"error": "Le champ 'question' est requis."}), 400

    # Le widget envoie son data-site-id : on ne cherche que dans les contenus de
    # ce site. Sans site_id, on cherche dans tout l'index (mode mono-site).
    result = answer(question, site_id=site_id)

    db.session.add(ChatLog(site_id=site_id, question=question, answer=result["answer"]))
    db.session.commit()

    return jsonify(result)


@bp.post("/ingest")
def ingest_any():
    """Endpoint admin : ingère n'importe quelle source, le type est détecté tout seul.

    Authorization: Bearer <ADMIN_TOKEN>
    Body JSON : {"source": "https://...", "site_id": "client-1", "max_pages": 50}

    `source` accepte une URL de site (HTML statique ou SPA), une API JSON, un
    sitemap.xml, un flux RSS/Atom, un CSV, un PDF, un chemin de fichier local,
    ou `supabase://table`. Omis, on retombe sur SCRAPER_TARGET_URL / SUPABASE_*.
    """
    if not _authorized():
        return jsonify({"error": "Non autorisé."}), 401

    data = request.get_json(silent=True) or {}
    max_pages = data.get("max_pages")

    report = ingest(
        target=data.get("source") or "",
        site_id=data.get("site_id"),
        max_pages=int(max_pages) if max_pages else None,
    )

    return jsonify(report), (200 if report["ok"] else 400)


@bp.post("/detect")
def detect_source():
    """Endpoint admin : dit quel type de source serait détecté, sans rien indexer.

    Authorization: Bearer <ADMIN_TOKEN>
    Body JSON : {"source": "https://..."}
    """
    if not _authorized():
        return jsonify({"error": "Non autorisé."}), 401

    detection = detect_only((request.get_json(silent=True) or {}).get("source") or "")
    detection.pop("peek", None)  # on ne renvoie pas le corps brut téléchargé
    return jsonify(detection)


@bp.post("/scrape/run")
def scrape_run():
    """Scraping HTML explicite (crawl de liens), sans détection automatique.

    Conservé pour compatibilité : préférer POST /api/ingest, qui choisit
    lui-même la meilleure stratégie (sitemap, API de plateforme, rendu JS...).

    Authorization: Bearer <ADMIN_TOKEN>
    Body JSON optionnel : {"url": "https://...", "site_id": "...", "render": true}
    """
    if not _authorized():
        return jsonify({"error": "Non autorisé."}), 401

    data = request.get_json(silent=True) or {}
    target = data.get("url") or Config.SCRAPER_TARGET_URL
    if not target:
        return jsonify({"error": "Aucune URL cible définie (SCRAPER_TARGET_URL ou body.url)."}), 400

    site_id = data.get("site_id") or Config.DEFAULT_SITE_ID
    pages = fetch_pages(target, max_pages=Config.SCRAPER_MAX_PAGES, render=bool(data.get("render")))
    parsed_documents = [doc for url, html in pages if (doc := parse_page(url, html, site_id=site_id))]
    created, updated = upsert_documents(parsed_documents)

    return jsonify({"pages_visited": len(pages), "created": created, "updated": updated, "site_id": site_id})


@bp.post("/sync/supabase")
def sync_supabase():
    """Synchronise les tables Supabase (SUPABASE_TABLES) vers `documents`.

    Authorization: Bearer <ADMIN_TOKEN>
    Body JSON optionnel : {"table": "trainings", "site_id": "..."}
    """
    if not _authorized():
        return jsonify({"error": "Non autorisé."}), 401

    if not Config.SUPABASE_URL or not Config.SUPABASE_ANON_KEY:
        return jsonify({"error": "SUPABASE_URL et SUPABASE_ANON_KEY doivent être définis."}), 400

    data = request.get_json(silent=True) or {}
    site_id = data.get("site_id") or Config.DEFAULT_SITE_ID
    only_table = data.get("table")

    if not only_table and not Config.SUPABASE_TABLES:
        return jsonify({"error": "SUPABASE_TABLES est vide et aucune table n'a été passée dans le body."}), 400

    parsed_documents = fetch_supabase_documents(site_id=site_id, only_table=only_table)
    created, updated = upsert_documents(parsed_documents)

    return jsonify(
        {
            "tables": [only_table] if only_table else Config.SUPABASE_TABLES,
            "rows_fetched": len(parsed_documents),
            "created": created,
            "updated": updated,
            "site_id": site_id,
        }
    )
