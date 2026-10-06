"""Tests de bout en bout de l'API (scraping simulé, LLM simulé, Chroma réel)."""

import pytest

from scraper.parser import parse_page

PAGES = [
    {"url": "https://www.skapa.fr/", "depth": 0, "html":
        "<html><head><title>Accueil | Skapa</title></head><body><main><h1>Bienvenue</h1>"
        "<p>École du numérique basée à Paris.</p></main>"
        "<footer>Contact : 01 23 45 67 89 – contact@skapa.fr</footer></body></html>"},
    {"url": "https://www.skapa.fr/tarifs", "depth": 1, "html":
        "<html><head><title>Tarifs | Skapa</title></head><body><main><h1>Tarifs</h1>"
        "<p>La formation Python coûte 4900 euros.</p></main></body></html>"},
]


@pytest.fixture
def client(temp_store, monkeypatch):
    from app import api_agent, config, llm
    from scraper import pipeline

    monkeypatch.setattr(pipeline, "_crawl", lambda url, mp, md, progress: ((PAGES, 0, 2), "test"))
    monkeypatch.setattr(config, "ADMIN_TOKEN", "secret")
    monkeypatch.setattr(config, "SCRAPE_PUBLIC", False)
    monkeypatch.setattr(api_agent, "_is_private_host", lambda host: False)

    calls = []

    def fake_chat(system_prompt, messages):
        calls.append({"system": system_prompt, "messages": messages})
        return "réponse simulée"

    monkeypatch.setattr(llm, "chat", fake_chat)
    api_agent.app.config["TESTING"] = True
    c = api_agent.app.test_client()
    c.llm_calls = calls
    return c


def _scrape(client):
    from app import jobs
    r = client.post("/api/scrape/run", json={"url": "https://skapa.fr"},
                    headers={"Authorization": "Bearer secret"})
    assert r.status_code == 202, r.get_json()
    job = jobs.wait_for(r.get_json()["job_id"], timeout=30)
    assert job["status"] == "success", job
    return job


def test_scrape_requires_token(client):
    r = client.post("/api/scrape/run", json={"url": "https://skapa.fr"})
    assert r.status_code == 401


def test_scrape_rejects_bad_scheme(client):
    r = client.post("/api/scrape/run", json={"url": "ftp://skapa.fr"},
                    headers={"Authorization": "Bearer secret"})
    assert r.status_code == 400


def test_chat_before_scrape_says_site_not_indexed(client):
    r = client.post("/chat", json={"message": "Prix ?", "site_url": "https://skapa.fr"})
    assert r.status_code == 200
    assert r.get_json()["indexed"] is False
    assert client.llm_calls == []


def test_full_flow_scrape_then_chat_uses_site_content(client):
    job = _scrape(client)
    assert job["result"]["pages_scraped"] == 2
    assert job["result"]["source_domain"] == "skapa.fr"

    # site_url SANS www alors que les pages sont sur www. -> doit quand même trouver
    r = client.post("/chat", json={"message": "Combien coûte la formation Python ?",
                                   "site_url": "https://skapa.fr"})
    data = r.get_json()
    assert r.status_code == 200, data
    assert data["indexed"] is True
    assert data["site_filter"] == "skapa.fr"
    system = client.llm_calls[-1]["system"]
    assert "4900 euros" in system                 # le bon contenu arrive au LLM
    assert "01 23 45 67 89" in system             # + le bloc contact du footer
    assert any(s["url"] == "https://www.skapa.fr/tarifs" for s in data["sources"])


def test_rescrape_replaces_old_chunks(client, temp_store):
    from app.chroma_client import get_collection
    from scraper.ingest import ingest_chunks

    ingest_chunks(parse_page("https://www.skapa.fr/ancienne-page",
                             "<title>Vieux</title><p>Contenu périmé supprimé du site.</p>"))
    _scrape(client)
    urls = {m["url"] for m in get_collection().get(include=["metadatas"])["metadatas"]}
    assert "https://www.skapa.fr/ancienne-page" not in urls


def test_other_sites_are_not_mixed(client):
    from scraper.ingest import ingest_chunks
    ingest_chunks(parse_page("https://autre-site.com/",
                             "<title>Autre</title><p>La formation Python coûte 10 euros ici.</p>"))
    _scrape(client)
    client.post("/chat", json={"message": "prix formation Python", "site_url": "https://www.skapa.fr"})
    assert "10 euros" not in client.llm_calls[-1]["system"]


def test_history_is_forwarded(client):
    _scrape(client)
    client.post("/chat", json={
        "message": "et le prix ?", "site_url": "https://skapa.fr",
        "history": [{"role": "user", "content": "Parle-moi de Python"},
                    {"role": "assistant", "content": "C'est une formation."}],
    })
    roles = [m["role"] for m in client.llm_calls[-1]["messages"]]
    assert roles == ["user", "assistant", "user"]


def test_site_status_endpoint(client):
    _scrape(client)
    data = client.get("/api/site?url=https://skapa.fr").get_json()
    assert data["indexed"] is True and data["pages"] == 2
