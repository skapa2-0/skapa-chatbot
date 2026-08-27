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

_raw_origins = os.environ.get("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = (
    [o.strip() for o in _raw_origins.split(",")]
    if "," in _raw_origins
    else _raw_origins
)
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL      = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
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
        "servers": [{"url": (os.environ.get("API_PUBLIC_URL") or request.host_url.rstrip("/"))}],
        "tags": [
            {"name": "1. Health check"},
            {"name": "2. Scraping"},
            {"name": "3. Documents"},
            {"name": "4. Chat"},
        ],
        "paths": {
            "/": {
                "get": {
                    "tags": ["1. Health check"],
                    "summary": "① Health check — vérifier que l'API tourne",
                    "description": (
                        "Vérifie que l'API est opérationnelle et indique combien de chunks "
                        "sont actuellement indexés dans ChromaDB (`chunks_in_db`). "
                        "\n\n**Ordre d'utilisation :**\n"
                        "1. `GET /` — vérifier que l'API tourne\n"
                        "2. `POST /api/scrape/run` — indexer un site web\n"
                        "3. `GET /api/documents` — vérifier ce qui a été indexé\n"
                        "4. `POST /chat` — poser des questions sur le contenu indexé\n\n"
                        "⚠️ Sans scraping préalable (`/api/scrape/run`), "
                        "la base est vide et `/chat` ne pourra pas répondre."
                    ),
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
            "/api/scrape/run": {
                "post": {
                    "summary": "② Indexer un site web (scraping)",
                    "description": (
                        "**Étape 1 obligatoire avant tout.** "
                        "Crawle le site depuis l'URL de départ, suit tous les liens internes, "
                        "nettoie le HTML, découpe le contenu en chunks et les indexe dans ChromaDB.\n\n"
                        "Sans cette étape, `/api/documents` retourne une liste vide "
                        "et `/chat` répond qu'il n'a pas d'informations.\n\n"
                        "**Authentification requise** : clique sur 🔒 Authorize en haut de cette page "
                        "et entre ton `ADMIN_TOKEN` avant d'exécuter."
                    ),
                    "tags": ["2. Scraping"],
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
            "/api/documents": {
                "get": {
                    "summary": "③ Vérifier ce qui a été indexé",
                    "description": (
                        "**Étape 2 (optionnelle mais recommandée).** "
                        "Retourne le journal des pages indexées (url, titre, date, nombre de chunks). "
                        "Utilise cette route pour confirmer que le scraping s'est bien passé "
                        "avant d'interroger `/chat`.\n\n"
                        "Si la liste est vide, relance `POST /api/scrape/run` d'abord."
                    ),
                    "tags": ["3. Documents"],
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
            "/chat": {
                "post": {
                    "summary": "④ Poser une question au chatbot",
                    "description": (
                        "**Étape 3 — uniquement après le scraping.** "
                        "Envoie un message à l'assistant RAG. "
                        "Le chatbot cherche les chunks les plus pertinents dans ChromaDB "
                        "et génère une réponse basée exclusivement sur ce contenu.\n\n"
                        "⚠️ **Prérequis** : `POST /api/scrape/run` doit avoir été exécuté au moins une fois. "
                        "Si `sources_used` vaut `0` dans la réponse, le site n'est pas encore indexé.\n\n"
                        "Si `site_url` est fourni, la recherche est limitée aux documents de ce domaine. "
                        "Sinon, tous les documents indexés sont consultés."
                    ),
                    "tags": ["4. Chat"],
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
                                        "indexed": True,
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


def _is_broad_site_question(message):
    text = message.lower()
    markers = (
        "quelles sont", "quels sont", "quelle sont", "liste", "toutes", "tous",
        "disponible", "disponibles", "formations", "formation", "services",
        "offre", "offres", "programmes", "programme", "catégories", "categories",
        "what are", "which", "all", "available", "list",
    )
    return any(marker in text for marker in markers)


# Formation-specific question markers.  When detected, extra query variants
# are injected so that the formation's page chunk scores above generic pages.
_FORMATION_QUESTION_MARKERS = {
    "prérequis":   ["prérequis requis niveau attendu", "conditions d'accès formation"],
    "coût":        ["tarif prix inter intra formation", "combien coûte"],
    "coute":       ["tarif prix inter intra formation", "combien coûte"],
    "prix":        ["tarif prix inter intra formation", "coût formation"],
    "tarif":       ["tarif prix inter intra", "coût formation"],
    "durée":       ["durée jours formation", "combien de jours"],
    "module":      ["modules programme contenu formation", "plan de formation"],
    "programme":   ["programme contenu modules formation", "plan de cours"],
    "objectif":    ["objectifs pédagogiques formation", "compétences visées"],
    "adresse":     ["public visé profils participants", "pour qui cette formation"],
    "public":      ["public visé profils cible", "pour qui cette formation"],
}


def _retrieve_context(collection, user_message, source_domain=None):
    """Retrieval RAG avec diversité de pages et plusieurs formulations de requête."""
    broad = _is_broad_site_question(user_message)
    text_lower = user_message.lower()

    queries = [user_message]
    if broad:
        # Une question globale est souvent trop vague pour un seul embedding.
        queries.extend([
            "liste complète des formations et programmes disponibles",
            "noms des formations disponibles sur le site",
            "pages formations programmes catalogue",
        ])
    else:
        # For formation-specific questions, add semantic variants so the
        # formation page chunk ranks above generic homepage/FAQ chunks.
        for marker, variants in _FORMATION_QUESTION_MARKERS.items():
            if marker in text_lower:
                queries.extend(variants)
                break

    where = {"source_domain": source_domain} if source_domain else None
    raw = collection.query(
        query_texts=queries,
        n_results=24 if broad else 10,
        where=where,
    )

    # Fusion + déduplication. On garde au maximum 3 chunks par URL pour éviter
    # qu'une longue page monopolise tout le contexte.
    candidates = []
    documents_by_query = raw.get("documents", [])
    metadatas_by_query = raw.get("metadatas", [])
    distances_by_query = raw.get("distances", [])
    for qi, docs in enumerate(documents_by_query):
        metas = metadatas_by_query[qi] if qi < len(metadatas_by_query) else []
        distances = distances_by_query[qi] if qi < len(distances_by_query) else []
        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            key = meta.get("url", "") + "#" + str(meta.get("chunk_index", i))
            candidates.append((key, doc, meta, distances[i] if i < len(distances) else 999.0))

    seen = set()
    per_url = {}
    selected = []
    limit = 24 if broad else 10
    for key, doc, meta, distance in sorted(candidates, key=lambda x: x[3]):
        if key in seen:
            continue
        seen.add(key)
        url = meta.get("url", "")
        if per_url.get(url, 0) >= (3 if broad else 2):
            continue
        per_url[url] = per_url.get(url, 0) + 1
        selected.append((doc, meta))
        if len(selected) >= limit:
            break

    blocks = []
    for doc, meta in selected:
        source = meta.get("url", "source inconnue") if meta else "source inconnue"
        title = meta.get("title", "") if meta else ""
        heading = meta.get("heading", "") if meta else ""
        prefix = f"[Source: {source}"
        if title:
            prefix += f" | Titre: {title}"
        if heading:
            prefix += f" | Section: {heading}"
        prefix += "]"
        blocks.append(f"{prefix}\n{doc}")

    # Protection contre un contexte énorme tout en gardant beaucoup plus
    # d'informations qu'avant.
    context = "\n\n---\n\n".join(blocks)
    return context, len(selected)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message")

    if not user_message:
        return jsonify({"error": "Missing 'message' field"}), 400
    if claude is None:
        return jsonify({"error": "ANTHROPIC_API_KEY is not configured on the server"}), 500

    try:
        collection = get_collection()
    except Exception as exc:
        return jsonify({"error": f"Vector database unavailable: {exc}"}), 500

    site_url = data.get("site_url")
    source_domain = urlparse(site_url).netloc if site_url else None
    # Silently ignore site_url values that have no recognisable host
    # (e.g. "skapa-academy.com" without a scheme yields an empty netloc).
    if site_url and not source_domain:
        parsed = urlparse("https://" + site_url)
        source_domain = parsed.netloc or None

    try:
        context, sources_used = _retrieve_context(collection, user_message, source_domain)
    except Exception as exc:
        return jsonify({"error": f"Retrieval failed: {exc}"}), 500

    if not context:
        context = "(Aucune information trouvée dans la base pour l'instant.)"

    system_prompt = (
        "Tu es un assistant de site web. Réponds UNIQUEMENT à partir du contexte fourni. "
        "Pour une question demandant une liste, donne toutes les informations présentes "
        "dans le contexte et ne prétends pas que la liste est exhaustive si le contexte "
        "ne permet pas de le garantir. Si l'information n'y est pas, dis clairement que tu ne sais pas.\n\n"
        f"CONTEXTE:\n{context}"
    )

    try:
        response = claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:
        return jsonify({"error": f"LLM request failed: {exc}"}), 500

    reply_text = "".join(block.text for block in response.content if block.type == "text")
    return jsonify({
        "reply": reply_text,
        "sources_used": sources_used,
        "indexed": sources_used > 0,
        "site_filter": source_domain or "all",
    })


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

    # Validate that the URL is a reachable http/https address.
    _parsed = urlparse(target_url)
    if _parsed.scheme not in ("http", "https") or not _parsed.netloc:
        return jsonify({"error": "Invalid URL: must start with http:// or https://"}), 400

    max_pages = data.get("max_pages")
    max_depth = data.get("max_depth")

    from scraper.pipeline import run_pipeline

    try:
        result = run_pipeline(
            target_url=target_url,
            max_pages=max_pages,
            max_depth=max_depth,
        )
    except Exception as exc:
        return jsonify({"error": f"Scraping failed: {exc}", "status": "error"}), 500

    return jsonify(result)


@app.route("/api/documents", methods=["GET"])
def list_documents():
    limit = request.args.get("limit", default=50, type=int)
    pages = get_recent_pages(limit=limit)
    return jsonify({"count": len(pages), "documents": pages})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
