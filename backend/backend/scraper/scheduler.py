"""
Rafraîchissement périodique : relance le pipeline de scraping toutes les
SCRAPER_INTERVAL_HOURS heures.

A lancer comme un PROCESSUS SÉPARÉ de l'API (pas dans le même process
gunicorn), par exemple :

    python -m scraper.scheduler

Important : ce process ne doit pas tourner en même temps qu'un autre
process qui écrit dans le même dossier Chroma en mode persistant
(Chroma ne supporte pas deux écrivains simultanés sur le même dossier).
En prod, préfère un cron qui appelle /api/scrape/run (voir docker-compose.yml).
"""

import os
import time

from apscheduler.schedulers.blocking import BlockingScheduler

from scraper.pipeline import run_pipeline

INTERVAL_HOURS = float(os.environ.get("SCRAPER_INTERVAL_HOURS", 24))


def main():
    scheduler = BlockingScheduler()
    scheduler.add_job(run_pipeline, "interval", hours=INTERVAL_HOURS, next_run_time=None)

    print(f"[scheduler] scraping toutes les {INTERVAL_HOURS}h. Premier run maintenant...")
    run_pipeline()  # premier run immédiat

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
