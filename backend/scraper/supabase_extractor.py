"""
supabase_extractor.py
----------------------
Récupère toutes les données du site Skapa Academy directement depuis
l'API PostgREST de Supabase, avec pagination complète (Range headers),
retries, et sauvegarde en JSON brut par table.

Prérequis : voir 01_TROUVER_API_SUPABASE.md pour obtenir SUPABASE_URL
et SUPABASE_ANON_KEY.

Usage:
    python supabase_extractor.py
"""

import os
import json
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

# Liste des tables à récupérer. Renseigne les vrais noms trouvés à l'étape 1
# (via /rest/v1/ qui liste le schéma OpenAPI, cf. 01_TROUVER_API_SUPABASE.md).
# Exemples plausibles pour un site de formations, à AJUSTER :
TABLES = os.environ.get(
    "SUPABASE_TABLES",
    "trainings,training_sessions,pages,categories,testimonials,faq",
).split(",")

PAGE_SIZE = 1000  # PostgREST limite généralement à 1000 par requête
OUT_DIR = Path("data/raw")
OUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Accept": "application/json",
}


def discover_tables_from_openapi() -> list[str]:
    """Interroge le schéma OpenAPI public de PostgREST pour lister les tables
    réellement accessibles. Utile pour vérifier/compléter TABLES."""
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/", headers=HEADERS, timeout=30)
    resp.raise_for_status()
    spec = resp.json()
    paths = spec.get("paths", {})
    tables = sorted(p.strip("/") for p in paths if p not in ("/",))
    return tables


def fetch_table(table: str) -> list[dict]:
    """Récupère toutes les lignes d'une table via pagination par Range header."""
    all_rows: list[dict] = []
    offset = 0
    session = requests.Session()
    session.headers.update(HEADERS)

    with tqdm(desc=f"Table {table}", unit="rows") as pbar:
        while True:
            headers = {"Range-Unit": "items", "Range": f"{offset}-{offset + PAGE_SIZE - 1}"}
            url = f"{SUPABASE_URL}/rest/v1/{table}?select=*&order=id.asc"

            for attempt in range(3):
                try:
                    resp = session.get(url, headers=headers, timeout=30)
                    if resp.status_code in (200, 206):
                        break
                    if resp.status_code in (401, 403):
                        raise PermissionError(
                            f"Accès refusé à la table '{table}' (RLS). "
                            f"Passe par une Edge Function ou par Playwright."
                        )
                    time.sleep(2 * (attempt + 1))
                except requests.RequestException:
                    time.sleep(2 * (attempt + 1))
            else:
                print(f"⚠️  Échec définitif sur {table} à l'offset {offset}")
                break

            batch = resp.json()
            if not batch:
                break

            all_rows.extend(batch)
            pbar.update(len(batch))
            offset += PAGE_SIZE

            if len(batch) < PAGE_SIZE:
                break  # dernière page atteinte

    return all_rows


def main():
    print("→ Vérification du schéma disponible via OpenAPI...")
    try:
        available = discover_tables_from_openapi()
        print(f"Tables détectées côté API : {available}")
    except Exception as e:
        print(f"(Impossible de lister le schéma automatiquement : {e})")
        available = None

    tables_to_fetch = TABLES
    if available:
        missing = [t for t in tables_to_fetch if t not in available]
        if missing:
            print(f"⚠️  Ces tables ne semblent pas exposées : {missing}")

    summary = {}
    for table in tables_to_fetch:
        table = table.strip()
        if not table:
            continue
        try:
            rows = fetch_table(table)
        except PermissionError as e:
            print(f"⛔ {e}")
            continue

        out_path = OUT_DIR / f"{table}.json"
        out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        summary[table] = len(rows)
        print(f"✅ {table}: {len(rows)} lignes → {out_path}")

    print("\nRésumé :")
    for t, n in summary.items():
        print(f"  - {t}: {n}")

    if not summary:
        print(
            "\n❌ Aucune table récupérée. Le site bloque probablement l'accès "
            "direct (RLS strict / Edge Functions). Utilise playwright_deep_scraper.py."
        )


if __name__ == "__main__":
    main()
