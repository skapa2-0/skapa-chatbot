"""
scraper/parser.py
------------------
Fusionne les données brutes (data/raw/*.json venant de Supabase et/ou
data/pages/*.json venant de spider.py), les transforme en Documents
LangChain, les découpe en chunks, écrit documents.json, puis (optionnel)
les indexe dans Chroma ou FAISS.

Usage (depuis /opt/chatbot/backend) :
    python -m scraper.parser
    python -m scraper.parser --index chroma
    python -m scraper.parser --index faiss

Ou directement depuis ce dossier :
    python parser.py
    python parser.py --index chroma
"""

import argparse
import json
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

RAW_DIR = Path("data/raw")
PAGES_DIR = Path("data/pages")
OUT_FILE = Path("documents.json")

SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def clean_html(text: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_raw_table(table: str) -> list[dict]:
    path = RAW_DIR / f"{table}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def docs_from_supabase() -> list[dict]:
    """Transforme chaque table Supabase en une liste de 'documents logiques'
    avant découpage. Adapte les clés (title/description/...) aux vrais noms
    de colonnes trouvés dans tes tables."""
    docs = []
    if not RAW_DIR.exists():
        return docs

    # Index des formations par id, pour enrichir les sessions avec le titre/prix
    # de leur formation (sinon une session isolée n'est qu'un tas d'UUID sans
    # contexte exploitable pour le RAG).
    trainings_by_id = {t["id"]: t for t in load_raw_table("trainings") if t.get("id")}

    for path in RAW_DIR.glob("*.json"):
        table = path.stem
        rows = json.loads(path.read_text(encoding="utf-8"))

        for row in rows:
            text_parts = []

            # Enrichissement training_sessions -> trainings (jointure applicative)
            if table == "training_sessions" and row.get("training_id") in trainings_by_id:
                parent = trainings_by_id[row["training_id"]]
                text_parts.append(f"formation: {parent.get('title', '')}")
                if parent.get("price"):
                    text_parts.append(f"prix: {parent['price']}")
                if parent.get("duration"):
                    text_parts.append(f"duree: {parent['duration']}")

            for key, value in row.items():
                if isinstance(value, str) and len(value.strip()) > 2:
                    text_parts.append(f"{key}: {clean_html(value)}")
                elif isinstance(value, (dict, list)) and value:
                    # Colonnes JSON/JSONB (ex: contenu structuré d'une page) :
                    # on ne les jette plus, on les sérialise pour ne rien perdre.
                    text_parts.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
                elif isinstance(value, (int, float)) and key not in ("id",):
                    text_parts.append(f"{key}: {value}")

            if not text_parts:
                continue

            content = "\n".join(text_parts)
            title = row.get("title") or row.get("name") or row.get("page_name") or row.get("slug") or f"{table}#{row.get('id', '')}"

            docs.append(
                {
                    "page_content": content,
                    "metadata": {
                        "source": f"supabase:{table}",
                        "table": table,
                        "record_id": row.get("id"),
                        "title": title,
                        "slug": row.get("slug") or row.get("page_key"),
                        "url": row.get("url") or row.get("permalink"),
                    },
                }
            )
    return docs


def docs_from_pages() -> list[dict]:
    """Transforme chaque page scrapée par Playwright en document."""
    docs = []
    if not PAGES_DIR.exists():
        return docs

    for path in PAGES_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        content = data.get("content", "").strip()
        if len(content) < 40:
            continue  # page vide / erreur, on ignore

        docs.append(
            {
                "page_content": content,
                "metadata": {
                    "source": "playwright",
                    "title": data.get("title"),
                    "url": data.get("url"),
                },
            }
        )
    return docs


def chunk_documents(raw_docs: list[dict]) -> list[dict]:
    chunked = []
    for doc in raw_docs:
        chunks = SPLITTER.split_text(doc["page_content"])
        for i, chunk in enumerate(chunks):
            meta = dict(doc["metadata"])
            meta["chunk_index"] = i
            meta["chunk_total"] = len(chunks)
            chunked.append({"page_content": chunk, "metadata": meta})
    return chunked


def deduplicate(docs: list[dict]) -> list[dict]:
    """Supprime les doublons exacts (ex: même page trouvée par les deux méthodes)."""
    seen = set()
    unique = []
    for d in docs:
        key = d["page_content"].strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(d)
    return unique


def build_index(chunks: list[dict], backend: str):
    from langchain_core.documents import Document
    from langchain_huggingface import HuggingFaceEmbeddings

    lc_docs = [Document(page_content=c["page_content"], metadata=c["metadata"]) for c in chunks]
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2")

    if backend == "chroma":
        from langchain_chroma import Chroma
        store = Chroma.from_documents(lc_docs, embeddings, persist_directory="chroma_db")
        print(f"✅ Index Chroma créé dans ./chroma_db ({len(lc_docs)} chunks)")
        return store

    if backend == "faiss":
        from langchain_community.vectorstores import FAISS
        store = FAISS.from_documents(lc_docs, embeddings)
        store.save_local("faiss_index")
        print(f"✅ Index FAISS créé dans ./faiss_index ({len(lc_docs)} chunks)")
        return store

    raise ValueError(f"Backend inconnu: {backend}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", choices=["chroma", "faiss"], default=None,
                         help="Construit aussi l'index vectoriel (optionnel).")
    args = parser.parse_args()

    raw_docs = docs_from_supabase() + docs_from_pages()
    print(f"→ {len(raw_docs)} documents bruts collectés "
          f"({len(list(RAW_DIR.glob('*.json'))) if RAW_DIR.exists() else 0} tables Supabase, "
          f"{len(list(PAGES_DIR.glob('*.json'))) if PAGES_DIR.exists() else 0} pages Playwright)")

    if not raw_docs:
        print("❌ Aucune donnée trouvée. Lance d'abord supabase_extractor.py "
              "et/ou playwright_deep_scraper.py.")
        return

    chunks = chunk_documents(raw_docs)
    chunks = deduplicate(chunks)

    OUT_FILE.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {len(chunks)} chunks écrits dans {OUT_FILE}")

    if args.index:
        build_index(chunks, args.index)


if __name__ == "__main__":
    main()