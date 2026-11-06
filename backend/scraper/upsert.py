"""Écriture dans Chroma en ne recalculant QUE les embeddings des chunks modifiés.

Calculer un embedding (bge-m3 via Ollama) est l'étape la plus lente du scraping.
Un chunk dont le texte n'a pas changé garde son embedding : on met juste à jour
ses métadonnées (date de scraping…), ce qui ne coûte presque rien.
"""

BATCH_SIZE = 256


def upsert_changed(collection, chunks, existing_docs):
    """chunks : [{"id", "text", "metadata"}] ; existing_docs : {id: texte en base}.
    Retourne le nombre de chunks dont l'embedding a été (re)calculé."""
    changed = [c for c in chunks if existing_docs.get(c["id"]) != c["text"]]
    same = [c for c in chunks if existing_docs.get(c["id"]) == c["text"]]
    for i in range(0, len(changed), BATCH_SIZE):
        b = changed[i:i + BATCH_SIZE]
        collection.upsert(ids=[c["id"] for c in b], documents=[c["text"] for c in b],
                          metadatas=[c["metadata"] for c in b])
    for i in range(0, len(same), BATCH_SIZE):
        b = same[i:i + BATCH_SIZE]
        collection.update(ids=[c["id"] for c in b], metadatas=[c["metadata"] for c in b])
    return len(changed)


def existing_docs(collection, ids=None, where=None):
    """{id: texte} des chunks déjà en base (filtrés par ids ou par where)."""
    if ids is not None and not ids:
        return {}
    res = collection.get(ids=ids, where=where, include=["documents"])
    return dict(zip(res.get("ids", []), res.get("documents") or []))
