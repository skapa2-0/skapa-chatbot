"""
Rafraîchissement périodique : relance le pipeline toutes les
SCRAPER_INTERVAL_HOURS heures sur SCRAPER_TARGET_URL.

    cd backend && python -m scraper.scheduler

Ne pas lancer en même temps que l'API sur le même dossier Chroma
(un seul processus écrivain). En prod, préfère un cron qui appelle
POST /api/scrape/run (voir docker-compose.yml).
"""

from apscheduler.schedulers.blocking import BlockingScheduler

from app import config
from scraper.pipeline import run_pipeline

INTERVAL_HOURS = config.env_float("SCRAPER_INTERVAL_HOURS", 24)


def main():
    scheduler = BlockingScheduler()
    scheduler.add_job(run_pipeline, "interval", hours=INTERVAL_HOURS)

    print(f"[scheduler] scraping toutes les {INTERVAL_HOURS}h. Premier run maintenant...")
    run_pipeline()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
