"""Spec OpenAPI pour /api/documents."""


def documents_path():
    return {
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
                    "content": {"application/json": {"example": {
                        "count": 2,
                        "documents": [
                            {
                                "url": "https://skapa-academy.com",
                                "title": "Skapa Academy",
                                "scraped_at": "2026-08-25T10:00:00+00:00",
                                "nb_chunks": 12,
                            }
                        ],
                    }}},
                }
            },
        }
    }
