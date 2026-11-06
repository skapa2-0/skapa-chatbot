"""Routes de santé : / et /health/db."""

from flask import jsonify

from app import llm
from app.api_agent import app
from app.chroma_client import get_collection, get_embedding_info, get_health_status


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Chatbot API is running"})


@app.route("/health/db", methods=["GET"])
def health_db():
    try:
        status, reason = get_health_status()
        body = {
            "status": status,
            "chunks_in_db": get_collection().count(),
            "embedding": get_embedding_info(),
            "llm": llm.describe(),
        }
        if reason:
            body["degraded_reason"] = reason
        return jsonify(body)
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 500
