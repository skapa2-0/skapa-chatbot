"""
Exécution du scraping en tâche de fond.

Avant : /api/scrape/run faisait tout le crawl DANS la requête HTTP.
gunicorn tue un worker au bout de 30 s par défaut -> sur un vrai site
(dizaines de pages) l'analyse plantait systématiquement en prod et le
navigateur attendait sans fin. Maintenant l'API répond tout de suite
avec un job_id, et le front interroge /api/scrape/status/<job_id>.

Les jobs sont en mémoire : lancer gunicorn avec UN seul worker
(--workers 1 --threads 8), ce qui est de toute façon requis pour Chroma
en mode fichier (un seul processus écrivain).
"""

import threading
import time
import traceback
import uuid

from scraper.spider import domain_key

_jobs = {}
_lock = threading.Lock()
_running_domains = set()

# Durée de rétention des jobs terminés (1 heure)
_JOB_TTL = 3600


def _public(job):
    return {k: v for k, v in job.items() if not k.startswith("_")}


def start_scrape_job(url, max_pages=None, max_depth=None):
    domain = domain_key(url)
    with _lock:
        for job in _jobs.values():
            if job["domain"] == domain and job["status"] in ("queued", "running"):
                return _public(job), False  # déjà en cours : on renvoie le job existant
        job_id = uuid.uuid4().hex[:12]
        job = {
            "job_id": job_id,
            "status": "queued",
            "url": url,
            "domain": domain,
            "pages_done": 0,
            "current_url": None,
            "result": None,
            "error": None,
            "started_at": time.time(),
            "finished_at": None,
        }
        _jobs[job_id] = job

    def progress(n, current_url):
        job["pages_done"] = n
        job["current_url"] = current_url

    def run():
        from scraper.pipeline import run_pipeline
        job["status"] = "running"
        try:
            result = run_pipeline(url, max_pages=max_pages, max_depth=max_depth, progress=progress)
            job["result"] = result
            if result.get("status") == "success":
                job["status"] = "success"
            else:
                job["status"] = "error"
                job["error"] = result.get("error", "Échec du scraping")
        except Exception as exc:
            traceback.print_exc()
            job["status"] = "error"
            job["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            job["finished_at"] = time.time()

    threading.Thread(target=run, name=f"scrape-{job_id}", daemon=True).start()
    _purge_old_jobs()
    return _public(job), True


def _purge_old_jobs():
    """Supprime les jobs terminés depuis plus de _JOB_TTL secondes."""
    cutoff = time.time() - _JOB_TTL
    with _lock:
        stale = [jid for jid, j in _jobs.items()
                 if j["status"] in ("success", "error") and (j.get("finished_at") or 0) < cutoff]
        for jid in stale:
            del _jobs[jid]


def get_job(job_id):
    job = _jobs.get(job_id)
    return _public(job) if job else None


def wait_for(job_id, timeout=600):
    """Utilisé par les tests / le mode synchrone."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = _jobs.get(job_id)
        if job and job["status"] in ("success", "error"):
            return _public(job)
        time.sleep(0.2)
    return get_job(job_id)
