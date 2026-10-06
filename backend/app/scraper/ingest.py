"""
Ingestion : écrit les chunks produits par parser.py dans Chroma DB.

replace_domain_chunks() remplace TOUT le contenu d'un site d'un coup :
avant, upsert() seul laissait en base les anciens chunks quand une page
raccourcissait ou disparaissait du site (réponses périmées).
"""

from app.chroma_client import get_collection

BATCH_SIZE = 256


def ingest_chunks(chunks):
    """Ajoute / met à jour des chunks {"id", "text", "metadata"}."""
    if not chunks:
        return 0
    collection = get_collection()
    # dédoublonnage des ids (Chroma refuse les doublons dans un même appel)
    unique = list({c["id"]: c for c in chunks}.values())
    for i in range(0, len(unique), BATCH_SIZE):
        batch = unique[i:i + BATCH_SIZE]
        collection.upsert(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )
    return len(unique)


def delete_domain(source_domain):
    collection = get_collection()
    existing = collection.get(where={"source_domain": source_domain}, include=[])
    ids = existing.get("ids", [])
    for i in range(0, len(ids), 5000):
        collection.delete(ids=ids[i:i + 5000])
    return len(ids)


def replace_domain_chunks(source_domain, chunks):
    """Insère les nouveaux chunks PUIS supprime les anciens.
    L'ordre upsert-first garantit qu'un crash en cours de suppression
    ne laisse pas le site sans aucun contenu dans Chroma."""
    added = ingest_chunks(chunks)
    # Calcule les IDs à garder AVANT de supprimer, pour éviter de supprimer
    # les chunks qu'on vient juste d'upsert.
    new_ids = {c["id"] for c in chunks}
    collection = get_collection()
    existing = collection.get(where={"source_domain": source_domain}, include=[])
    stale = [id_ for id_ in existing.get("ids", []) if id_ not in new_ids]
    for i in range(0, len(stale), 5000):
        collection.delete(ids=stale[i:i + 5000])
    print(f"[ingest] {source_domain}: {added} ajoutés, {len(stale)} anciens chunks supprimés")
    return added


def count_domain(source_domain):
    res = get_collection().get(where={"source_domain": source_domain}, include=[])
    return len(res.get("ids", []))
