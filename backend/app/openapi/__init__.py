"""Spécification OpenAPI (affichée sur /docs)."""

import os

from app.openapi.chat import chat_path
from app.openapi.documents import documents_path
from app.openapi.health import health_path
from app.openapi.scrape import scrape_run_path, scrape_status_path, site_path


def build_spec():
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Chatbot API",
            "description": (
                "API de chatbot RAG générique. "
                "Scrapez n'importe quel site web, puis posez des questions sur son contenu."
            ),
            "version": "2.0.0",
        },
        "servers": [{"url": os.environ.get("PUBLIC_API_URL", "http://localhost:8000")}],
        "paths": {
            "/": health_path(),
            "/chat": chat_path(),
            "/api/documents": documents_path(),
            "/api/scrape/run": scrape_run_path(),
            "/api/scrape/status/{job_id}": scrape_status_path(),
            "/api/site": site_path(),
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "token"}
            }
        },
    }
