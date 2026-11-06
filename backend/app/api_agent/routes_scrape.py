"""Routes de scraping : POST /api/scrape/run et GET /api/scrape/status/<job_id>."""

from urllib.parse import urlparse

from flask import jsonify, request

from app import api_agent, jobs
from app.api_agent import ALLOW_PRIVATE_URLS, app
from app.api_agent import public_guard
from app.api_agent.admin_guard import check_admin
from scraper.spider import domain_key, normalize_url


def _parse_url(data):
    """Retourne (url_normalisée, erreur_json_or_None, status_code)."""
    target_url = str(data.get("url") or "").strip()
    if not target_url:
        return None, {"error": "Missing 'url' field"}, 400
    if "://" not in target_url:
        target_url = "https://" + target_url
    parsed = urlparse(target_url)
    if parsed.scheme not in ("http", "https"):
        return None, {"error": "URL must use http or https scheme"}, 400
    if not parsed.hostname:
        return None, {"error": "Invalid URL: missing host"}, 400

    private = api_agent._is_private_host(parsed.hostname)
    if private is None:
        return None, {"error": f"Domaine introuvable : {parsed.hostname}"}, 400
    if private and not ALLOW_PRIVATE_URLS:
        return None, {"error": "Les adresses internes / privées ne sont pas autorisées"}, 400
    return target_url, None, 200


def _int(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


@app.route("/api/scrape/run", methods=["POST"])
def run_scrape():
    denied = check_admin()
    if denied:
        return denied

    data = request.get_json(silent=True) or {}
    target_url, err, code = _parse_url(data)
    if err:
        return jsonify(err), code

    job, created = jobs.start_scrape_job(
        normalize_url(target_url),
        max_pages=_int(data.get("max_pages")),
        max_depth=_int(data.get("max_depth")),
    )

    if data.get("wait"):
        job = jobs.wait_for(job["job_id"])
        return jsonify({**(job.get("result") or {}), "job_id": job["job_id"],
                        "status": job["status"], "error": job.get("error")}), \
            (200 if job["status"] == "success" else 502)

    return jsonify({**job, "status_url": f"/api/scrape/status/{job['job_id']}",
                    "already_running": not created}), 202


@app.route("/api/scrape/start", methods=["POST"])
def start_scrape():
    """Endpoint du front : aucun token côté navigateur (ADMIN_TOKEN reste dans
    le .env). Comme il est public, il est bridé côté serveur :
      - limite de lancements par IP (SCRAPE_PUBLIC_RATE par heure)
      - nombre de scrapings simultanés limité (SCRAPE_PUBLIC_MAX_JOBS)
      - pages / profondeur plafonnées (max_pages, max_depth et wait du client ignorés)
      - un site indexé il y a moins de SCRAPE_PUBLIC_COOLDOWN_HOURS n'est pas
        re-scrapé : on renvoie l'index existant (personne ne peut l'écraser en boucle)
      - SCRAPE_ALLOWED_DOMAINS (optionnel) : seuls ces domaines sont acceptés
    """
    from app import config as _cfg

    if not _cfg.SCRAPE_PUBLIC and not _cfg.ADMIN_TOKEN:
        return jsonify({"error": "Scraping is not configured on this server"}), 503

    data = request.get_json(silent=True) or {}
    target_url, err, code = _parse_url(data)
    if err:
        return jsonify(err), code
    target_url = normalize_url(target_url)
    domain = domain_key(target_url)

    allowed = public_guard.allowed_domains()
    if allowed and domain not in allowed:
        return jsonify({"error": "Ce site n'est pas autorisé sur cette démo."}), 403

    cached = public_guard.recent_index(domain)
    if cached:
        return jsonify(cached), 200

    if public_guard.running_public_jobs() >= public_guard.MAX_JOBS:
        return jsonify({"error": "Trop d'analyses en cours, réessayez dans quelques minutes."}), 429

    if not public_guard.hit_rate_limit(public_guard.client_ip(request)):
        return jsonify({"error": "Limite d'analyses atteinte, réessayez plus tard."}), 429

    job, created = jobs.start_scrape_job(
        target_url,
        max_pages=public_guard.MAX_PAGES,
        max_depth=public_guard.MAX_DEPTH,
    )
    return jsonify({**job, "status_url": f"/api/scrape/status/{job['job_id']}",
                    "already_running": not created}), 202


@app.route("/api/scrape/status/<job_id>", methods=["GET"])
def scrape_status(job_id):
    job = jobs.get_job(job_id)
    if not job:
        return jsonify({"error": "Job inconnu (le serveur a peut-être redémarré)"}), 404
    return jsonify(job)
