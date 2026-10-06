# Configuration gunicorn (chargée automatiquement depuis backend/).
#
# - 1 seul worker : Chroma en mode fichier n'accepte qu'un processus
#   écrivain, et le suivi des jobs de scraping est en mémoire.
# - des threads : le chat continue de répondre pendant un scraping.
# - timeout large : une réponse LLM locale (Ollama) peut prendre du temps.
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = 1
threads = int(os.environ.get("GUNICORN_THREADS", 8))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 300))
graceful_timeout = 30
accesslog = "-"
