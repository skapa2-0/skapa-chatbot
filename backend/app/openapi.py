"""Spécification OpenAPI (affichée sur /docs)."""

import os


def build_spec():
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
        "servers": [{"url": os.environ.get("PUBLIC_API_URL", "http://localhost:8000")}],
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
                                        "platform_name": {
                                            "type": "string",
                                            "description": (
                                                "Nom lisible de la plateforme (optionnel). "
                                                "S'il est absent, le nom est déduit automatiquement "
                                                "depuis le domaine de site_url."
                                            ),
                                            "example": "Simplon",
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
                                    "marque blanche (nom explicite)": {
                                        "value": {
                                            "message": "Quelles sont les formations ?",
                                            "site_url": "https://www.simplon.co",
                                            "platform_name": "Simplon",
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
                                        "platform_name": "Skapa Academy",
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
                        "503": {
                            "description": "Ollama inaccessible ou modèle non chargé",
                            "content": {
                                "application/json": {
                                    "example": {"error": "Impossible de joindre Ollama sur http://localhost:11434"}
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
    _patch(spec)
    return spec


def _patch(spec):
    """Endpoints ajoutés : scraping asynchrone + statut + /api/site."""
    run = spec["paths"]["/api/scrape/run"]["post"]
    run["description"] += (
        "\n\nLe scraping tourne **en tâche de fond** : la réponse 202 contient un "
        "`job_id` à suivre via `GET /api/scrape/status/{job_id}`. "
        "Ajouter `\"wait\": true` pour attendre le résultat (scripts / cron)."
    )
    run["responses"]["202"] = {
        "description": "Scraping lancé",
        "content": {"application/json": {"example": {
            "job_id": "a1b2c3d4e5f6", "status": "queued", "url": "https://skapa-academy.com/",
            "domain": "skapa-academy.com", "pages_done": 0,
            "status_url": "/api/scrape/status/a1b2c3d4e5f6"}}},
    }
    chat_props = spec["paths"]["/chat"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]
    chat_props["history"] = {
        "type": "array",
        "description": "Derniers échanges (optionnel) pour les questions de relance",
        "items": {"type": "object", "properties": {
            "role": {"type": "string", "enum": ["user", "assistant"]},
            "content": {"type": "string"}}},
    }
    spec["paths"]["/api/scrape/status/{job_id}"] = {"get": {
        "summary": "Progression d'un scraping",
        "operationId": "scrapeStatus",
        "parameters": [{"name": "job_id", "in": "path", "required": True, "schema": {"type": "string"}}],
        "responses": {"200": {"description": "Statut (queued | running | success | error)",
                              "content": {"application/json": {"example": {
                                  "job_id": "a1b2c3d4e5f6", "status": "running", "pages_done": 12,
                                  "current_url": "https://skapa-academy.com/formations"}}}},
                      "404": {"description": "Job inconnu"}},
    }}
    spec["paths"]["/api/site"] = {"get": {
        "summary": "Le site est-il indexé ?",
        "operationId": "siteStatus",
        "parameters": [{"name": "url", "in": "query", "required": True, "schema": {"type": "string"}}],
        "responses": {"200": {"description": "Nombre de chunks du site",
                              "content": {"application/json": {"example": {
                                  "source_domain": "skapa-academy.com", "indexed": True, "chunks": 142}}}}},
    }}
