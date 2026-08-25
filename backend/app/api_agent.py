"""
API du chatbot Skapa.

Deux routes utiles :
  GET  /                 -> health check
  POST /chat              -> pose une question, reçoit une réponse basée
                             sur les infos scrapées (RAG simple)
  POST /api/scrape/run    -> relance le scraping manuellement (protégé)

Tout est volontairement simple : pas de framework en plus de Flask,
pas de queue, pas de worker séparé.
"""

import os
import sys

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from anthropic import Anthropic

# Permet de faire "from scraper.xxx import yyy" même quand ce fichier
# est lancé depuis backend/app/ (utile en local / gunicorn).
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.chroma_client import get_collection  # noqa: E402
from app.metadata import get_recent_pages  # noqa: E402

load_dotenv()

app = Flask(__name__)

# ALLOWED_ORIGINS : un seul domaine (flask-cors ne gère pas une liste
# séparée par des virgules). Mets "*" en dev, ton domaine en prod.
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

claude = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


@app.route("/", methods=["GET"])
def health():
    collection = get_collection()
    return jsonify(
        {
            "status": "ok",
            "message": "Chatbot API is running",
            "chunks_in_db": collection.count(),
        }
    )


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message")

    if not user_message:
        return jsonify({"error": "Missing 'message' field"}), 400

    if claude is None:
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured on the server"}), 500

    collection = get_collection()

    # 1. On cherche les passages les plus proches de la question dans Chroma.
    results = collection.query(query_texts=[user_message], n_results=5)
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    if documents:
        context_blocks = []
        for doc, meta in zip(documents, metadatas):
            source = meta.get("url", "source inconnue") if meta else "source inconnue"
            context_blocks.append(f"[Source: {source}]\n{doc}")
        context = "\n\n---\n\n".join(context_blocks)
    else:
        context = "(Aucune information trouvée dans la base pour l'instant.)"

    system_prompt = (
        "Tu es l'assistant du site. Réponds UNIQUEMENT à partir du "
        "contexte fourni ci-dessous. Si l'information n'y est pas, "
        "dis clairement que tu ne sais pas, ne l'invente pas.\n\n"
        f"CONTEXTE:\n{context}"
    )

    response = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    reply_text = "".join(
        block.text for block in response.content if block.type == "text"
    )

    return jsonify({"reply": reply_text, "sources_used": len(documents)})


@app.route("/api/documents", methods=["GET"])
def list_documents():
    """
    Expose le jeu de données (métadonnées des pages indexées) pour
    qu'un autre composant puisse l'exploiter directement, sans passer
    par le chatbot. Requête SQL d'extraction sur la base SQLite de
    métadonnées (voir app/metadata.py).
    """
    limit = request.args.get("limit", default=50, type=int)
    pages = get_recent_pages(limit=limit)
    return jsonify({"count": len(pages), "documents": pages})


@app.route("/api/scrape/run", methods=["POST"])
def run_scrape():
    """Relance le scraping + l'indexation à la demande (protégé par token)."""
    if not ADMIN_TOKEN:
        return jsonify({"error": "ADMIN_TOKEN is not configured on the server"}), 500

    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {ADMIN_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

    # Import différé pour ne pas charger playwright/bs4 au démarrage de l'API
    # si on ne s'en sert pas tout de suite.
    from scraper.pipeline import run_pipeline

    result = run_pipeline()
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
