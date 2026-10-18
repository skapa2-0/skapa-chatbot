"""Constantes du crawler, chargées depuis l'environnement une seule fois."""

from app import config

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 (compatible; SkapaChatbot/1.0)"
)
USER_AGENT = config.env("SCRAPER_USER_AGENT", BROWSER_UA)
MAX_PAGES = config.env_int("SCRAPER_MAX_PAGES", 100)
MAX_DEPTH = config.env_int("SCRAPER_MAX_DEPTH", 5)
DELAY_SECONDS = config.env_float("SCRAPER_DELAY_SECONDS", 0.0)
REQUEST_TIMEOUT = config.env_float("SCRAPER_REQUEST_TIMEOUT", 10)
PLAYWRIGHT_TIMEOUT = config.env_int("SCRAPER_PLAYWRIGHT_TIMEOUT", 15000)
RESPECT_ROBOTS = config.env_bool("SCRAPER_RESPECT_ROBOTS", False)
USE_SITEMAP = config.env_bool("SCRAPER_USE_SITEMAP", True)
MAX_WORKERS = config.env_int("SCRAPER_WORKERS", 5)

SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp",
    ".zip", ".rar", ".7z", ".gz", ".tar", ".mp4", ".mp3", ".avi", ".mov", ".webm",
    ".wav", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".json",
    ".xml", ".css", ".js", ".woff", ".woff2", ".ttf", ".eot", ".dmg", ".exe",
)
SKIP_PATH_PARTS = ("/wp-admin", "/wp-login", "/wp-json", "/cart", "/panier",
                   "/checkout", "/login", "/logout", "/feed", "/xmlrpc")
TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "mc_", "_ga", "ref", "replytocom")
