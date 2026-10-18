"""Spec OpenAPI pour /chat."""


def chat_path():
    return {
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
                                "history": {
                                    "type": "array",
                                    "description": "Derniers échanges (optionnel) pour les questions de relance",
                                    "items": {"type": "object", "properties": {
                                        "role": {"type": "string", "enum": ["user", "assistant"]},
                                        "content": {"type": "string"}}},
                                },
                            },
                        },
                        "examples": {
                            "sans filtre": {"value": {"message": "Bonjour"}},
                            "avec filtre domaine": {"value": {
                                "message": "Quelles sont les formations ?",
                                "site_url": "https://skapa-academy.com",
                            }},
                            "marque blanche (nom explicite)": {"value": {
                                "message": "Quelles sont les formations ?",
                                "site_url": "https://www.simplon.co",
                                "platform_name": "Simplon",
                            }},
                        },
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Réponse du chatbot",
                    "content": {"application/json": {"example": {
                        "reply": "Voici les formations disponibles...",
                        "sources_used": 3,
                        "site_filter": "skapa-academy.com",
                        "platform_name": "Skapa Academy",
                    }}},
                },
                "400": {
                    "description": "Champ 'message' manquant",
                    "content": {"application/json": {"example": {"error": "Missing 'message' field"}}},
                },
                "503": {
                    "description": "Ollama inaccessible ou modèle non chargé",
                    "content": {"application/json": {"example": {
                        "error": "Impossible de joindre Ollama sur http://localhost:11434"}}},
                },
            },
        }
    }
