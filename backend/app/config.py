"""
Configuration centrale.

Charge backend/.env AVANT toute lecture de variable (avant, le .env était
chargé après l'import de chroma_client/metadata, donc CHROMA_DIR et
METADATA_DB du .env étaient ignorés quand on lançait sans start.sh).
Les chemins relatifs sont résolus par rapport au dossier backend/, pour
que la base Chroma soit toujours la même quel que soit le dossier courant.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")  # fallback : .env à la racine


def env(name, default=None):
    value = os.environ.get(name)
    if value is None:
        return default
    # Tolère les commentaires en fin de ligne non gérés par certains outils
    value = value.split(" #")[0].strip()
    return value if value != "" else default


def env_int(name, default):
    try:
        return int(env(name, default))
    except (TypeError, ValueError):
        return default


def env_float(name, default):
    try:
        return float(env(name, default))
    except (TypeError, ValueError):
        return default


def env_bool(name, default=False):
    value = env(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def resolve_path(value):
    p = Path(value)
    return str(p if p.is_absolute() else (BACKEND_DIR / p).resolve())


CHROMA_DIR = resolve_path(env("CHROMA_DIR", "./chroma_db"))
METADATA_DB = resolve_path(env("METADATA_DB", "./metadata.db"))
COLLECTION_BASE = env("CHROMA_COLLECTION", "web_knowledge")

# ── LLM ──────────────────────────────────────────────────────────────────────
# ollama (défaut, local) | anthropic (utile en prod : Railway ne fait pas tourner Ollama)
LLM_PROVIDER = env("LLM_PROVIDER", "ollama").lower()
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = env("OLLAMA_MODEL", "llama3.2")
OLLAMA_NUM_CTX = env_int("OLLAMA_NUM_CTX", 8192)
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
LLM_TIMEOUT = env_float("LLM_TIMEOUT", 180)

# ── Embeddings ───────────────────────────────────────────────────────────────
# auto    -> modèle d'embedding Ollama s'il est installé, sinon modèle Chroma par défaut
# ollama  -> toujours Ollama (OLLAMA_EMBED_MODEL, multilingue recommandé : bge-m3)
# default -> modèle intégré de Chroma (all-MiniLM-L6-v2, anglais surtout)
EMBEDDING_PROVIDER = env("EMBEDDING_PROVIDER", "auto").lower()
OLLAMA_EMBED_MODEL = env("OLLAMA_EMBED_MODEL", "bge-m3")

# ── RAG ──────────────────────────────────────────────────────────────────────
RAG_TOP_K = env_int("RAG_TOP_K", 6)

# ── Admin / sécurité ─────────────────────────────────────────────────────────
ADMIN_TOKEN = env("ADMIN_TOKEN")
# true -> /api/scrape/run accessible sans token (pratique en local / démo)
SCRAPE_PUBLIC = env_bool("SCRAPE_PUBLIC", False)
ALLOWED_ORIGINS = env("ALLOWED_ORIGINS", "*")
