"""
API du chatbot générique.

Routes :
  GET  /                  -> health check
  POST /chat               -> question au chatbot (RAG sur ChromaDB)
  GET  /api/documents      -> pages scrapées (SQLite)
  POST /api/scrape/run     -> lance le crawling sur une URL (protégé)
  GET  /openapi.json       -> spec OpenAPI
  GET  /docs/              -> Swagger UI
"""

import os
import sys
from urllib.parse import urlparse

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from dotenv import load_dotenv
from anthropic import Anthropic

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.chroma_client import get_collection  # noqa: E402
from app.metadata import get_recent_pages     # noqa: E402

load_dotenv()

app = Flask(__name__)

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL      = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")
ADMIN_TOKEN       = os.environ.get("ADMIN_TOKEN")

claude = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# --- Swagger UI ---
_swaggerui = get_swaggerui_blueprint(
    "/docs",
    "/openapi.json",
    config={"app_name": "Chatbot API"},
)
app.register_blueprint(_swaggerui, url_prefix="/docs")


@app.route("/openapi.json", methods=["GET"])
def openapi_spec():
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "Chatbot API",
            "description": (
                "API de chatbot RAG générique. "
                "Scrapez n'importe quel site web, puis posez des questions sur son contenu."
            ),
            "version": "2.0.0",
        },
        "servers": [{"url": "http://51.255.215.75:8000"}],
        "paths": {
            "/": {
                "get": {
                    "summary": "Health check",
                    "operationId": "health",
                    "responses": {
                        "200": {
                            "description": "API opérationnelle",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "status": "ok",
                                        "message": "Chatbot API is running",
                                        "chunks_in_db": 142,
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/chat": {
                "post": {
                    "summary": "Poser une question au chatbot",
                    "description": (
                        "Envoie un message à l'assistant RAG. "
                        "Si `site_url` est fourni, la recherche est limitée aux documents "
                        "de ce domaine. Sinon, tous les documents indexés sont consultés."
                    ),
                    "operationId": "chat",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["message"],
                                    "properties": {
                                        "message": {
                                            "type": "string",
                                            "description": "La question à poser",
                                            "example": "Quelles sont les formations disponibles ?",
                                        },
                                        "site_url": {
                                            "type": "string",
                                            "description": "Restreindre la recherche à ce domaine (optionnel)",
                                            "example": "https://skapa-academy.com",
                                        },
                                    },
                                },
                                "examples": {
                                    "sans filtre": {
                                        "value": {"message": "Bonjour"}
                                    },
                                    "avec filtre domaine": {
                                        "value": {
                                            "message": "Quelles sont les formations ?",
                                            "site_url": "https://skapa-academy.com",
                                        }
                                    },
                                },
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Réponse du chatbot",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "reply": "Voici les formations disponibles...",
                                        "sources_used": 3,
                                        "site_filter": "skapa-academy.com",
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "Champ 'message' manquant",
                            "content": {
                                "application/json": {
                                    "example": {"error": "Missing 'message' field"}
                                }
                            },
                        },
                        "500": {
                            "description": "Clé API Anthropic non configurée",
                            "content": {
                                "application/json": {
                                    "example": {"error": "ANTHROPIC_API_KEY is not configured on the server"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/documents": {
                "get": {
                    "summary": "Lister les pages scrapées",
                    "description": "Retourne le journal des pages indexées (SQLite).",
                    "operationId": "listDocuments",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "description": "Nombre max de résultats (défaut : 50)",
                            "schema": {"type": "integer", "default": 50, "example": 20},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Liste des pages",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "count": 2,
                                        "documents": [
                                            {
                                                "url": "https://skapa-academy.com",
                                                "title": "Skapa Academy",
                                                "scraped_at": "2026-08-25T10:00:00+00:00",
                                                "nb_chunks": 12,
                                            }
                                        ],
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/scrape/run": {
                "post": {
                    "summary": "Lancer le crawling sur une URL",
                    "description": (
                        "Crawle le site depuis l'URL de départ, suit les liens internes, "
                        "indexe tout le contenu dans ChromaDB. "
                        "**Authentification requise** : clique sur 🔒 Authorize et entre ton ADMIN_TOKEN."
                    ),
                    "operationId": "runScrape",
                    "security": [{"BearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["url"],
                                    "properties": {
                                        "url": {
                                            "type": "string",
                                            "description": "URL de départ du crawling",
                                            "example": "https://skapa-academy.com",
                                        },
                                        "max_pages": {
                                            "type": "integer",
                                            "description": "Nombre max de pages à scraper (défaut : 100)",
                                            "example": 50,
                                        },
                                        "max_depth": {
                                            "type": "integer",
                                            "description": "Profondeur max de crawling (défaut : 5)",
                                            "example": 3,
                                        },
                                    },
                                },
                                "examples": {
                                    "crawl simple": {
                                        "value": {"url": "https://skapa-academy.com"}
                                    },
                                    "crawl limité": {
                                        "value": {
                                            "url": "https://skapa-academy.com",
                                            "max_pages": 20,
                                            "max_depth": 2,
                                        }
                                    },
                                },
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Crawling terminé",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "status": "success",
                                        "start_url": "https://skapa-academy.com",
                                        "pages_scraped": 25,
                                        "pages_failed": 2,
                                        "chunks_created": 150,
                                        "urls_found": 42,
                                        "duration_seconds": 38.4,
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "URL manquante dans le body",
                            "content": {
                                "application/json": {
                                    "example": {"error": "Missing 'url' field"}
                                }
                            },
                        },
                        "401": {
                            "description": "Token admin invalide ou absent",
                            "content": {
                                "application/json": {
                                    "example": {"error": "Unauthorized"}
                                }
                            },
                        },
                        "500": {
                            "description": "ADMIN_TOKEN non configuré",
                            "content": {
                                "application/json": {
                                    "example": {"error": "ADMIN_TOKEN is not configured on the server"}
                                }
                            },
                        },
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "token",
                }
            }
        },
    }
    return jsonify(spec)


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

    # Filtrage par domaine si site_url fourni
    site_url = data.get("site_url")
    source_domain = urlparse(site_url).netloc if site_url else None

    query_kwargs = {"query_texts": [user_message], "n_results": 5}
    if source_domain:
        query_kwargs["where"] = {"source_domain": source_domain}

    results = collection.query(**query_kwargs)
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
        "Tu es l'Assistant Skapa, le chatbot officiel de Skapa Academy.\n\n"
        "Skapa Academy est un organisme de formation français certifié Qualiopi, "
        "spécialisé en Design, Product Management et Intelligence Artificielle.\n\n"
        "Tu réponds aux questions des visiteurs concernant :\n"
        "- Les formations disponibles (Design, Product Management, IA)\n"
        "- Les tarifs des formations\n"
        "- Le financement via OPCO et autres dispositifs\n"
        "- La certification Qualiopi\n"
        "- Les modalités d'inscription\n\n"
        "Règles absolues :\n"
        "- Réponds TOUJOURS en français, de façon courte et professionnelle\n"
        "- Utilise uniquement les informations du contexte fourni ci-dessous\n"
        "- Si la réponse n'est pas dans le contexte, indique que tu ne disposes pas "
        "de cette information et invite le visiteur à contacter Skapa Academy directement\n"
        "- Si la question ne concerne pas Skapa Academy, refuse poliment et recentre "
        "la conversation sur les sujets Skapa Academy\n\n"
        f"CONTEXTE :\n{context}"
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

    return jsonify({
        "reply": reply_text,
        "sources_used": len(documents),
        "site_filter": source_domain or "all",
    })


@app.route("/api/documents", methods=["GET"])
def list_documents():
    limit = request.args.get("limit", default=50, type=int)
    pages = get_recent_pages(limit=limit)
    return jsonify({"count": len(pages), "documents": pages})


@app.route("/api/scrape/run", methods=["POST"])
def run_scrape():
    if not ADMIN_TOKEN:
        return jsonify({"error": "ADMIN_TOKEN is not configured on the server"}), 500

    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {ADMIN_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    target_url = data.get("url")
    if not target_url:
        return jsonify({"error": "Missing 'url' field"}), 400

    max_pages = data.get("max_pages")
    max_depth = data.get("max_depth")

    from scraper.pipeline import run_pipeline

    result = run_pipeline(
        target_url=target_url,
        max_pages=max_pages,
        max_depth=max_depth,
    )
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
