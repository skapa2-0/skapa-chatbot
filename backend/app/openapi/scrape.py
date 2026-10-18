"""Spec OpenAPI pour /api/scrape/run, /api/scrape/status et /api/site."""


def scrape_run_path():
    return {
        "post": {
            "summary": "Lancer le crawling sur une URL",
            "description": (
                "Crawle le site depuis l'URL de départ, suit les liens internes, "
                "indexe tout le contenu dans ChromaDB. "
                "**Authentification requise** : clique sur 🔒 Authorize et entre ton ADMIN_TOKEN."
                "\n\nLe scraping tourne **en tâche de fond** : la réponse 202 contient un "
                "`job_id` à suivre via `GET /api/scrape/status/{job_id}`. "
                "Ajouter `\"wait\": true` pour attendre le résultat (scripts / cron)."
            ),
            "operationId": "runScrape",
            "security": [{"BearerAuth": []}],
            "requestBody": {
                "required": True,
                "content": {"application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["url"],
                        "properties": {
                            "url": {"type": "string",
                                    "description": "URL de départ du crawling",
                                    "example": "https://skapa-academy.com"},
                            "max_pages": {"type": "integer",
                                          "description": "Nombre max de pages à scraper (défaut : 100)",
                                          "example": 50},
                            "max_depth": {"type": "integer",
                                          "description": "Profondeur max de crawling (défaut : 5)",
                                          "example": 3},
                        },
                    },
                    "examples": {
                        "crawl simple": {"value": {"url": "https://skapa-academy.com"}},
                        "crawl limité": {"value": {
                            "url": "https://skapa-academy.com", "max_pages": 20, "max_depth": 2}},
                    },
                }},
            },
            "responses": {
                "200": {"description": "Crawling terminé (mode wait=true)",
                        "content": {"application/json": {"example": {
                            "status": "success", "start_url": "https://skapa-academy.com",
                            "pages_scraped": 25, "pages_failed": 2, "chunks_created": 150,
                            "urls_found": 42, "duration_seconds": 38.4,
                        }}}},
                "202": {"description": "Scraping lancé",
                        "content": {"application/json": {"example": {
                            "job_id": "a1b2c3d4e5f6", "status": "queued",
                            "url": "https://skapa-academy.com/", "domain": "skapa-academy.com",
                            "pages_done": 0, "status_url": "/api/scrape/status/a1b2c3d4e5f6"}}}},
                "400": {"description": "URL manquante dans le body",
                        "content": {"application/json": {"example": {"error": "Missing 'url' field"}}}},
                "401": {"description": "Token admin invalide ou absent",
                        "content": {"application/json": {"example": {"error": "Unauthorized"}}}},
                "500": {"description": "ADMIN_TOKEN non configuré",
                        "content": {"application/json": {"example": {
                            "error": "ADMIN_TOKEN is not configured on the server"}}}},
            },
        }
    }


def scrape_status_path():
    return {"get": {
        "summary": "Progression d'un scraping",
        "operationId": "scrapeStatus",
        "parameters": [{"name": "job_id", "in": "path", "required": True,
                        "schema": {"type": "string"}}],
        "responses": {
            "200": {"description": "Statut (queued | running | success | error)",
                    "content": {"application/json": {"example": {
                        "job_id": "a1b2c3d4e5f6", "status": "running", "pages_done": 12,
                        "current_url": "https://skapa-academy.com/formations"}}}},
            "404": {"description": "Job inconnu"},
        },
    }}


def site_path():
    return {"get": {
        "summary": "Le site est-il indexé ?",
        "operationId": "siteStatus",
        "parameters": [{"name": "url", "in": "query", "required": True,
                        "schema": {"type": "string"}}],
        "responses": {"200": {"description": "Nombre de chunks du site",
                              "content": {"application/json": {"example": {
                                  "source_domain": "skapa-academy.com",
                                  "indexed": True, "chunks": 142}}}}},
    }}
