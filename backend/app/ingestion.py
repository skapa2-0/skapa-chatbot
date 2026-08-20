"""Ingestion partagée : upsert des documents en base SQL + (ré)indexation Chroma.

Utilisée par toutes les sources de données (scraping HTML, API JSON,
WordPress, Shopify, CSV, PDF, Supabase, job planifié) : quel que soit le
type de plateforme d'origine, on arrive ici avec le même format de
document, donc une seule logique d'upsert et d'indexation.
"""
from .config import Config
from .models import Document, db
from .vectorstore import index_document

# Champs acceptés depuis les extracteurs (garde-fou : un extracteur ne peut pas
# injecter une clé inattendue dans le modèle SQLAlchemy).
_FIELDS = ("source_url", "title", "content", "external_id", "source_type", "site_id")


def upsert_documents(parsed_documents: list[dict]) -> tuple[int, int]:
    """Insère/MAJ une liste de documents en base SQL et les (ré)indexe dans Chroma.

    Retourne (nombre créés, nombre mis à jour).
    """
    created, updated = 0, 0

    for parsed in parsed_documents:
        fields = {key: parsed[key] for key in _FIELDS if key in parsed}
        fields.setdefault("source_type", "html")
        fields.setdefault("site_id", Config.DEFAULT_SITE_ID)

        doc = Document.query.filter_by(external_id=fields["external_id"]).first()
        if doc:
            doc.title = fields["title"]
            doc.content = fields["content"]
            doc.source_url = fields["source_url"]
            doc.source_type = fields["source_type"]
            doc.site_id = fields["site_id"]
            updated += 1
        else:
            doc = Document(**fields)
            db.session.add(doc)
            created += 1

        db.session.flush()  # garantit doc.id avant l'indexation vectorielle
        index_document(
            doc.id,
            doc.source_url,
            doc.title,
            doc.content,
            site_id=doc.site_id,
            source_type=doc.source_type,
        )

    db.session.commit()
    return created, updated
