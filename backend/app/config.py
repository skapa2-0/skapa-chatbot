import os

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "oui")


class Config:
    """Configuration centralisée, lue depuis les variables d'environnement (.env)."""

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///skapa.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change-me")

    SCRAPER_TARGET_URL = os.getenv("SCRAPER_TARGET_URL", "")
    SCRAPER_USER_AGENT = os.getenv("SCRAPER_USER_AGENT", "SkapaChatbotBot/1.0")
    SCRAPER_INTERVAL_HOURS = int(os.getenv("SCRAPER_INTERVAL_HOURS", "24"))
    SCRAPER_MAX_PAGES = int(os.getenv("SCRAPER_MAX_PAGES", "30"))

    # Rendu JavaScript (Playwright) pour les sites dont le contenu est monté
    # côté client (React/Vue/Angular) : "auto" décide page par page,
    # "always" force le navigateur, "never" reste sur requests (plus rapide).
    SCRAPER_RENDER_JS = os.getenv("SCRAPER_RENDER_JS", "auto").strip().lower()
    SCRAPER_RENDER_TIMEOUT_MS = int(os.getenv("SCRAPER_RENDER_TIMEOUT_MS", "15000"))

    # Un sitemap.xml liste toutes les pages : plus fiable qu'un crawl de liens.
    SCRAPER_PREFER_SITEMAP = _flag("SCRAPER_PREFER_SITEMAP", "true")
    SITEMAP_MAX_CHILDREN = int(os.getenv("SITEMAP_MAX_CHILDREN", "5"))

    # Source de données Supabase : lue directement via l'API REST (PostgREST),
    # en complément ou à la place du scraping HTML.
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_TABLES = [t.strip() for t in os.getenv("SUPABASE_TABLES", "").split(",") if t.strip()]

    # Identifiant du site propriétaire des données, quand le widget n'en envoie
    # pas : permet d'héberger plusieurs sites clients sur la même API.
    DEFAULT_SITE_ID = os.getenv("DEFAULT_SITE_ID", "default")

    TOP_K = int(os.getenv("CHATBOT_TOP_K", "4"))

    # Bornes de taille d'un document avant chunking.
    MIN_DOC_CHARS = int(os.getenv("MIN_DOC_CHARS", "40"))
    MAX_DOC_CHARS = int(os.getenv("MAX_DOC_CHARS", "50000"))

    # Délai réseau des requêtes d'ingestion (détection, APIs, fichiers).
    INGEST_TIMEOUT = int(os.getenv("INGEST_TIMEOUT", "15"))

    # Base vectorielle Chroma (RAG) : dossier de persistance sur disque
    CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")
    CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "300"))
    CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "40"))

    # Origines autorisées à interroger l'API depuis le widget (ex: sites clients)
    ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
