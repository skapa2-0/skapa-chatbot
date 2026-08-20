"""Source de données Supabase : lit des tables via l'API REST (PostgREST)
et les transforme en `Document` indexables par le chatbot.

Alternative (ou complément) au scraping HTML classique : si tes données
sont déjà structurées dans Supabase (formations, sessions, pages...),
pas besoin de scraper le site, on lit directement les tables.

Le schéma des tables n'a pas besoin d'être connu à l'avance : chaque ligne
est aplatie en "colonne: valeur" par `extractors.flatten`, donc n'importe
quelle table s'indexe telle quelle.
"""
import requests

from . import source_detector as sd
from .config import Config
from .extractors import flatten, guess_title, make_doc


def _row_to_document(table: str, row: dict, site_id: str) -> dict | None:
    row_id = row.get("id") or row.get("uuid") or row.get("slug")
    if row_id is None:
        return None

    title = guess_title(row, f"{table} #{row_id}")
    content = "\n".join([str(title), *flatten(row)])

    return make_doc(
        site_id,
        sd.SUPABASE,
        f"supabase://{table}/{row_id}",
        title,
        content,
        seed=f"{table}:{row_id}",
    )


def fetch_supabase_documents(site_id: str | None = None, only_table: str | None = None) -> list[dict]:
    """Interroge les tables SUPABASE_TABLES (ou seulement `only_table`) et retourne des documents.

    La clé anon respecte les règles RLS du projet : seules les lignes lisibles
    par cette clé sont synchronisées.
    """
    if not Config.SUPABASE_URL or not Config.SUPABASE_ANON_KEY:
        return []

    site_id = site_id or Config.DEFAULT_SITE_ID
    tables = [only_table] if only_table else Config.SUPABASE_TABLES
    if not tables:
        return []

    headers = {
        "apikey": Config.SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {Config.SUPABASE_ANON_KEY}",
    }

    documents: list[dict] = []
    for table in tables:
        url = f"{Config.SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
        try:
            response = requests.get(
                url,
                headers=headers,
                params={"select": "*", "limit": 1000},
                timeout=Config.INGEST_TIMEOUT,
            )
            response.raise_for_status()
            rows = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Supabase : échec de récupération de la table '{table}' : {exc}")
            continue

        for row in rows if isinstance(rows, list) else []:
            doc = _row_to_document(table, row, site_id)
            if doc:
                documents.append(doc)

    return documents
