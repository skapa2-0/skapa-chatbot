"""
Petite base SQLite qui trace les pages scrapées (métadonnées).
Complètement indépendante de Chroma : Chroma garde le texte + les
embeddings pour la recherche sémantique, SQLite garde juste un journal
"quelle page, quand, combien de chunks" -> utile pour la traçabilité
RGPD et pour prouver une vraie extraction SQL (C2) sur un modèle
physique réel (C4), sans toucher à l'architecture Chroma existante.
"""

import os
import sqlite3
from datetime import datetime, timezone

METADATA_DB = os.environ.get("METADATA_DB", "./metadata.db")


def get_connection(db_path=None):
    conn = sqlite3.connect(db_path or METADATA_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    """Modèle physique : une ligne = une page scrapée à un instant donné."""
    conn = get_connection(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scraped_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            title TEXT,
            scraped_at TEXT NOT NULL,
            nb_chunks INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def log_scraped_page(url, title, nb_chunks, db_path=None):
    """Import programmé (INSERT) à chaque page ingérée par le pipeline."""
    init_db(db_path)
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO scraped_pages (url, title, scraped_at, nb_chunks) VALUES (?, ?, ?, ?)",
        (url, title, datetime.now(timezone.utc).isoformat(), nb_chunks),
    )
    conn.commit()
    conn.close()


def get_recent_pages(limit=50, db_path=None):
    """Requête SQL d'extraction (SELECT) -> preuve C2."""
    init_db(db_path)
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT url, title, scraped_at, nb_chunks "
        "FROM scraped_pages ORDER BY scraped_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
