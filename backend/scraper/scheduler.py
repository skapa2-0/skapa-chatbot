"""Rafraîchissement périodique des données (APScheduler).

Réutilise l'ingestion universelle : la cible peut donc être un site HTML,
une API JSON, un sitemap, WordPress, Shopify, un CSV... sans changer ce
fichier. `SCRAPER_TARGET_URL` vide et `SUPABASE_*` renseigné -> la synchro
Supabase est prise automatiquement.
"""
from apscheduler.schedulers.background import BackgroundScheduler

from app import create_app
from app.config import Config
from app.universal_ingest import ingest


def run_scrape_job() -> None:
    app = create_app()
    with app.app_context():
        report = ingest(Config.SCRAPER_TARGET_URL)

        if not report["ok"]:
            print(f"Ingestion ignorée : {report['reason']}")
            return

        print(
            f"Ingestion terminée ({report['source_type']}) : "
            f"{report['documents']} documents, {report['created']} créés, {report['updated']} mis à jour."
        )


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_scrape_job, "interval", hours=Config.SCRAPER_INTERVAL_HOURS)
    scheduler.start()
    return scheduler


if __name__ == "__main__":
    run_scrape_job()
