#!/usr/bin/env python3
"""Relance l'analyse de tous les sites connus (tâche planifiée hebdomadaire).

Crontab recommandé :
  0 2 * * 0  cd /opt/chatbot/backend && python scripts/reanalyse_all.py >> /var/log/skapa_reanalyse.log 2>&1
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import jobs, metadata  # noqa: E402

sites = metadata.get_admin_sites()
if not sites:
    print("Aucun site à réanalyser.")
    sys.exit(0)

print(f"Réanalyse de {len(sites)} site(s)…")
for site in sites:
    domain = site["domain"]
    url = f"https://{domain}"
    job, created = jobs.start_scrape_job(url)
    if not created:
        print(f"[SKIP] {domain} — analyse déjà en cours")
        continue
    result = jobs.wait_for(job["job_id"])
    if result["status"] == "success":
        pages = result.get("result", {}).get("pages_scraped", "?")
        print(f"[OK]   {domain} — {pages} pages")
    else:
        print(f"[ERR]  {domain} — {result.get('error', 'inconnu')}")
