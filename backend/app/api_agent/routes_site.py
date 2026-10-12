"""Routes documents / sites : /api/site et /api/documents."""

from flask import jsonify, request

from app.api_agent import app
from app.api_agent.admin_guard import check_admin
from app.chroma_client import get_collection
from app.metadata import get_recent_pages
from scraper.spider import domain_key


@app.route("/api/site", methods=["GET"])
def site_status():
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "Missing 'url' parameter"}), 400
    domain = domain_key(url)
    res = get_collection().get(where={"source_domain": domain}, include=["metadatas"], limit=100000)
    metas = res.get("metadatas") or []
    pages = {m.get("url") for m in metas if m and m.get("kind", "page") == "page"}
    return jsonify({"source_domain": domain, "indexed": bool(metas),
                    "chunks": len(metas), "pages": len(pages)})


@app.route("/api/documents", methods=["GET"])
def list_documents():
    denied = check_admin()
    if denied:
        return denied
    limit = request.args.get("limit", default=50, type=int)
    pages = get_recent_pages(limit=limit)
    return jsonify({"count": len(pages), "documents": pages})
