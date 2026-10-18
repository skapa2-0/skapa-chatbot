"""API du chatbot (RAG sur ChromaDB).

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

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app import config  # noqa: E402  (charge le .env en tout premier)
from flask import Flask  # noqa: E402
from flask_cors import CORS  # noqa: E402

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

ALLOW_PRIVATE_URLS = config.env_bool("SCRAPER_ALLOW_PRIVATE_URLS", False)
MAX_HISTORY = 6

# Exposé ici pour autoriser le monkeypatching depuis les tests.
from app.api_agent.admin_guard import is_private_host as _is_private_host  # noqa: E402

# Charge les routes (chaque module décore `app` au moment de son import).
from app.api_agent import routes_chat, routes_docs, routes_health, routes_scrape, routes_site  # noqa: E402,F401
