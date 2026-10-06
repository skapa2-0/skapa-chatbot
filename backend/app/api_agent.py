"""
API du chatbot (RAG sur ChromaDB).

Routes :
  GET  /                           -> health check
  GET  /health/db                  -> nb de chunks + modèles utilisés
  POST /chat                       -> question au chatbot (RAG)
  GET  /api/site?url=...           -> le site est-il indexé ? (nb de chunks)
  GET  /api/documents              -> pages scrapées (SQLite)
  POST /api/scrape/run             -> lance le scraping d'une URL (tâche de fond)
  GET  /api/scrape/status/<job_id> -> progression / résultat du scraping
  GET  /openapi.json, /docs        -> spec OpenAPI + Swagger UI
"""

import ipaddress
import os
import socket
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import config  # noqa: E402  (charge le .env en tout premier)
from flask import Flask, jsonify, make_response, request  # noqa: E402
from flask_cors import CORS  # noqa: E402

from app import jobs, llm  # noqa: E402
from app.chroma_client import get_collection, get_embedding_info  # noqa: E402
from app.metadata import get_recent_pages  # noqa: E402
from app.openapi import build_spec  # noqa: E402
from scraper.spider import domain_key, normalize_url  # noqa: E402

app = Flask(__name__)

# Plusieurs origines possibles : "https://a.com,https://b.com"
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

ALLOW_PRIVATE_URLS = config.env_bool("SCRAPER_ALLOW_PRIVATE_URLS", False)
MAX_HISTORY = 6


# ── Docs ──────────────────────────────────────────────────────────────────────

@app.route("/openapi.json", methods=["GET"])
def openapi_spec():
    return jsonify(build_spec())


@app.route("/docs/", methods=["GET"])
@app.route("/docs", methods=["GET"])
def swagger_ui():
    html = """<!DOCTYPE html>
<html>
<head>
  <title>Chatbot API – Swagger UI</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
  SwaggerUIBundle({
    url: "/openapi.json",
    dom_id: '#swagger-ui',
    presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
    layout: "BaseLayout",
    deepLinking: true
  });
</script>
</body>
</html>"""
    r = make_response(html)
    r.headers["Content-Type"] = "text/html"
    return r


# ── Health ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Chatbot API is running"})


@app.route("/health/db", methods=["GET"])
def health_db():
    try:
        return jsonify({
            "status": "ok",
            "chunks_in_db": get_collection().count(),
            "embedding": get_embedding_info(),
            "llm": llm.describe(),
        })
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500


# ── Helpers ───────────────────────────────────────────────────────────────────

def _default_platform_name(domain):
    if not domain:
        return "ce site"
    name = domain.split(".")[0].replace("-", " ").replace("_", " ")
    return name.title()


def _domain_count(domain):
    res = get_collection().get(where={"source_domain": domain}, include=[], limit=100000)
    return len(res.get("ids", []))


def _clean_history(raw):
    if not isinstance(raw, list):
        return []
    out = []
    for m in raw[-MAX_HISTORY:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = str(m.get("content") or "").strip()[:2000]
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    # l'historique doit commencer par un message utilisateur et alterner
    while out and out[0]["role"] != "user":
        out.pop(0)
    merged = []
    for m in out:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] += "\n" + m["content"]
        else:
            merged.append(m)
    if merged and merged[-1]["role"] == "user":
        merged.pop()  # le message courant est ajouté à la fin
    return merged


def _query(collection, text, domain, n):
    kwargs = {"query_texts": [text], "n_results": n,
              "include": ["documents", "metadatas", "distances"]}
    if domain:
        kwargs["where"] = {"source_domain": domain}
    res = collection.query(**kwargs)
    return [
        {"text": d, "meta": m or {}, "distance": dist}
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]


def _retrieve(query, domain, followup_query=None):
    collection = get_collection()
    total = collection.count()
    if total == 0:
        return []
    k = min(config.RAG_TOP_K, total)
    try:
        hits = _query(collection, query, domain, k)
        # Question de relance (« et le prix ? ») : on complète avec une recherche
        # qui inclut la question précédente, sans écraser la question actuelle.
        if followup_query:
            seen = {h["text"] for h in hits}
            extra = [h for h in _query(collection, followup_query, domain, k) if h["text"] not in seen]
            hits = hits[: max(3, k - 2)] + extra[:2]
    except Exception as exc:
        app.logger.exception("Recherche Chroma échouée : %s", exc)
        raise
    # Toujours joindre le bloc « coordonnées » du site s'il existe (contact, adresse…)
    if domain and not any(h["meta"].get("kind") == "site_info" for h in hits):
        info = collection.get(where={"$and": [{"source_domain": domain}, {"kind": "site_info"}]},
                              include=["documents", "metadatas"], limit=1)
        if info.get("ids"):
            hits.append({"text": info["documents"][0], "meta": info["metadatas"][0], "distance": None})
    return hits


# ── Chat ──────────────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = str(data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "Missing 'message' field"}), 400
    user_message = user_message[:2000]

    site_url = data.get("site_url")
    source_domain = domain_key(site_url) if site_url else None
    platform_name = data.get("platform_name") or _default_platform_name(source_domain)
    history = _clean_history(data.get("history"))

    if source_domain and _domain_count(source_domain) == 0:
        return jsonify({
            "reply": (f"Je n'ai pas encore de contenu pour {source_domain}. "
                      "Lancez d'abord l'analyse du site (« Analyser et adapter »), "
                      "puis reposez votre question."),
            "sources_used": 0, "sources": [],
            "site_filter": source_domain, "platform_name": platform_name,
            "indexed": False,
        })

    # Pour une relance courte (« et le prix ? »), on cherche aussi avec la question précédente
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
    followup = f"{last_user}\n{user_message}" if last_user and len(user_message) < 60 else None

    try:
        hits = _retrieve(user_message, source_domain, followup)
    except Exception as exc:
        return jsonify({"error": f"Recherche dans la base impossible : {exc}"}), 503

    if hits:
        context = "\n\n---\n\n".join(
            f"[Source : {h['meta'].get('url', 'inconnue')}]\n{h['text']}" for h in hits
        )
    else:
        context = "(Aucune information trouvée dans la base pour l'instant.)"

    domain_hint = f" ({source_domain})" if source_domain else ""
    system_prompt = (
        f"Tu es l'assistant virtuel officiel du site {platform_name}{domain_hint}.\n\n"
        "Règles absolues :\n"
        "- Réponds dans la langue du visiteur (français par défaut), de façon courte, claire et professionnelle\n"
        "- Utilise UNIQUEMENT les informations du CONTEXTE ci-dessous (extraits du site)\n"
        "- Quand c'est utile, donne le lien de la page source (URL complète)\n"
        f"- Si la réponse n'est pas dans le contexte, dis honnêtement que tu ne disposes pas "
        f"de cette information et invite le visiteur à contacter {platform_name} directement\n"
        f"- Si la question ne concerne pas {platform_name}, recentre poliment la conversation\n"
        "- N'invente jamais de prix, de date, de nom ou de coordonnées\n\n"
        f"CONTEXTE :\n{context}"
    )

    try:
        reply_text = llm.chat(system_prompt, [*history, {"role": "user", "content": user_message}])
    except llm.LLMError as exc:
        return jsonify({"error": str(exc)}), 503

    sources, seen = [], set()
    for h in hits:
        url = h["meta"].get("url")
        if url and url not in seen and h["meta"].get("kind") != "site_info":
            seen.add(url)
            sources.append({"url": url, "title": h["meta"].get("title", "")})

    return jsonify({
        "reply": reply_text or "Je n'ai pas pu formuler de réponse.",
        "sources_used": len(hits),
        "sources": sources[:3],
        "site_filter": source_domain or "all",
        "platform_name": platform_name,
        "indexed": bool(hits),
    })


# ── Sites / documents ─────────────────────────────────────────────────────────

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
    denied = _check_admin()
    if denied:
        return denied
    limit = request.args.get("limit", default=50, type=int)
    pages = get_recent_pages(limit=limit)
    return jsonify({"count": len(pages), "documents": pages})


# ── Scraping ──────────────────────────────────────────────────────────────────

def _check_admin():
    if config.SCRAPE_PUBLIC:
        return None
    if not config.ADMIN_TOKEN:
        return jsonify({"error": "ADMIN_TOKEN is not configured on the server"}), 500
    if request.headers.get("Authorization", "") != f"Bearer {config.ADMIN_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401
    return None


def _is_private_host(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return None  # introuvable
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


@app.route("/api/scrape/run", methods=["POST"])
def run_scrape():
    denied = _check_admin()
    if denied:
        return denied

    data = request.get_json(silent=True) or {}
    target_url = str(data.get("url") or "").strip()
    if not target_url:
        return jsonify({"error": "Missing 'url' field"}), 400
    if "://" not in target_url:
        target_url = "https://" + target_url

    parsed = urlparse(target_url)
    if parsed.scheme not in ("http", "https"):
        return jsonify({"error": "URL must use http or https scheme"}), 400
    if not parsed.hostname:
        return jsonify({"error": "Invalid URL: missing host"}), 400

    private = _is_private_host(parsed.hostname)
    if private is None:
        return jsonify({"error": f"Domaine introuvable : {parsed.hostname}"}), 400
    if private and not ALLOW_PRIVATE_URLS:  # protection SSRF
        return jsonify({"error": "Les adresses internes / privées ne sont pas autorisées"}), 400

    def _int(v):
        try:
            return int(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    job, created = jobs.start_scrape_job(
        normalize_url(target_url),
        max_pages=_int(data.get("max_pages")),
        max_depth=_int(data.get("max_depth")),
    )

    if data.get("wait"):  # mode synchrone (scripts / cron)
        job = jobs.wait_for(job["job_id"])
        return jsonify({**(job.get("result") or {}), "job_id": job["job_id"],
                        "status": job["status"], "error": job.get("error")}), \
            (200 if job["status"] == "success" else 502)

    return jsonify({**job, "status_url": f"/api/scrape/status/{job['job_id']}",
                    "already_running": not created}), 202


@app.route("/api/scrape/status/<job_id>", methods=["GET"])
def scrape_status(job_id):
    job = jobs.get_job(job_id)
    if not job:
        return jsonify({"error": "Job inconnu (le serveur a peut-être redémarré)"}), 404
    return jsonify(job)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    # threaded=True : le scraping tourne en fond pendant que le chat répond
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True, use_reloader=False)
