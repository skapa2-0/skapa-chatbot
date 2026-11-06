"""/api/scrape/start : public (pas de token côté front) mais bridé côté serveur."""

import pytest

from app.tests.test_api import PAGES


@pytest.fixture
def client(temp_store, monkeypatch):
    from app import api_agent, config
    from app.api_agent import public_guard
    from scraper import pipeline

    seen = []

    def fake_crawl(url, mp, md, progress):
        seen.append((mp, md))
        return (PAGES, 0, 2), "test"

    monkeypatch.setattr(pipeline, "_crawl", fake_crawl)
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    monkeypatch.setattr(config, "SCRAPE_PUBLIC", False)
    monkeypatch.setattr(api_agent, "_is_private_host", lambda host: False)
    monkeypatch.delenv("SCRAPE_ALLOWED_DOMAINS", raising=False)
    public_guard.reset_for_tests()
    c = api_agent.app.test_client()
    c.crawl_args = seen
    yield c
    public_guard.reset_for_tests()


def _start(client, url="https://skapa.fr", ip="1.2.3.4", **extra):
    return client.post("/api/scrape/start", json={"url": url, **extra},
                       headers={"X-Forwarded-For": ip})


def _wait(resp):
    from app import jobs
    return jobs.wait_for(resp.get_json()["job_id"], timeout=30)


def test_start_works_without_token_and_caps_pages(client):
    r = _start(client, max_pages=5000, max_depth=50, wait=True)
    assert r.status_code == 202                      # « wait » ignoré
    assert _wait(r)["status"] == "success"
    from app.api_agent import public_guard
    assert client.crawl_args[-1] == (public_guard.MAX_PAGES, public_guard.MAX_DEPTH)


def test_recently_indexed_site_is_not_rescraped(client):
    _wait(_start(client))
    n = len(client.crawl_args)
    r = _start(client, ip="9.9.9.9")
    data = r.get_json()
    assert r.status_code == 200 and data["cached"] is True
    assert data["site_url"] == "https://www.skapa.fr/"
    assert data["pages_scraped"] == 2
    assert data["site_title"] == "Skapa"
    assert len(client.crawl_args) == n               # aucun nouveau crawl


def test_rate_limit_per_ip(client, monkeypatch):
    from app.api_agent import public_guard
    monkeypatch.setattr(public_guard, "COOLDOWN_HOURS", 0)
    monkeypatch.setattr(public_guard, "RATE_PER_HOUR", 2)
    for i in range(2):
        _wait(_start(client, url=f"https://site{i}.fr"))
    assert _start(client, url="https://site9.fr").status_code == 429
    # une autre IP n'est pas bloquée ; une IP inventée à gauche du XFF ne contourne rien
    assert _start(client, url="https://site9.fr", ip="5.5.5.5").status_code == 202
    r = _start(client, url="https://site8.fr", ip="6.6.6.6, 1.2.3.4")
    assert r.status_code == 429


def test_allowed_domains(client, monkeypatch):
    monkeypatch.setenv("SCRAPE_ALLOWED_DOMAINS", "www.skapa.fr, autre.com")
    assert _start(client, url="https://evil.com").status_code == 403
    assert _start(client, url="https://skapa.fr").status_code == 202


def test_admin_route_still_requires_token(client):
    r = client.post("/api/scrape/run", json={"url": "https://skapa.fr"})
    assert r.status_code == 401
