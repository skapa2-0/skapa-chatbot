"""
Petite base SQLite qui trace les pages scrapées (métadonnées).
Indépendante de Chroma : Chroma garde le texte + les embeddings pour la
recherche sémantique, SQLite garde un journal "quelle page, quand,
combien de chunks" (traçabilité RGPD).
"""

import sqlite3
import threading
from datetime import datetime, timezone

from app import config

# Une connexion par fichier (avant : une seule connexion globale qui
# ignorait db_path après le premier appel).
_conns = {}
_lock = threading.Lock()


def _get_conn(db_path=None):
    path = db_path or config.METADATA_DB
    with _lock:
        conn = _conns.get(path)
        if conn is None:
            conn = sqlite3.connect(path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS scraped_pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT,
                    scraped_at TEXT NOT NULL,
                    nb_chunks INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS sites (
                    domain TEXT PRIMARY KEY,
                    brand_color TEXT,
                    site_title TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
            _conns[path] = conn
        return conn


def get_connection(db_path=None):
    return _get_conn(db_path)


def init_db(db_path=None):
    _get_conn(db_path)


def log_scraped_page(url, title, nb_chunks, db_path=None):
    conn = _get_conn(db_path)
    # Ne pas tenir le verrou pendant le commit (bloque sinon tous les threads).
    # sqlite3 avec check_same_thread=False est thread-safe en écriture sérialisée.
    conn.execute(
        "INSERT INTO scraped_pages (url, title, scraped_at, nb_chunks) VALUES (?, ?, ?, ?)",
        (url, title, datetime.now(timezone.utc).isoformat(), nb_chunks),
    )
    conn.commit()


def upsert_site(domain: str, brand_color: "str | None", site_title: "str | None",
                db_path=None) -> None:
    conn = _get_conn(db_path)
    conn.execute(
        "INSERT INTO sites (domain, brand_color, site_title, updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(domain) DO UPDATE SET brand_color=excluded.brand_color, "
        "site_title=excluded.site_title, updated_at=excluded.updated_at",
        (domain, brand_color, site_title, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def get_site(domain: str, db_path=None) -> "dict | None":
    row = _get_conn(db_path).execute(
        "SELECT domain, brand_color, site_title, updated_at FROM sites WHERE domain=?",
        (domain,),
    ).fetchone()
    return dict(row) if row else None


def delete_site(domain: str, db_path=None) -> None:
    conn = _get_conn(db_path)
    conn.execute("DELETE FROM sites WHERE domain=?", (domain,))
    conn.commit()


def get_recent_pages(limit=50, db_path=None):
    conn = _get_conn(db_path)
    rows = conn.execute(
        "SELECT url, title, scraped_at, nb_chunks "
        "FROM scraped_pages ORDER BY scraped_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
