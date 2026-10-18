"""Spec OpenAPI pour /."""


def health_path():
    return {
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
    }
