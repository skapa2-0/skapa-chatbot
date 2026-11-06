"""Qualité des réponses : plan du site, questions « liste », liens cités, titres."""

import pytest

from app.api_agent.chat_prompt import cited_links
from app.api_agent.rag_helpers import _diverse, is_list_query
from scraper.pipeline.titles import distinct_titles, path_label

BASE = "https://exemple.fr"
SAME = "<html><head><title>Exemple Academy</title></head><body><h1>{h1}</h1>" \
       "<main><p>{body}</p></main></body></html>"
PAGES = [
    {"url": BASE + "/", "depth": 0, "html": SAME.format(h1="Accueil", body="Bienvenue " * 40)},
    {"url": BASE + "/formations/python", "depth": 1,
     "html": SAME.format(h1="Formation Python", body="Python 12 semaines 4900 euros. " * 15)},
    {"url": BASE + "/formations/data", "depth": 1,
     "html": SAME.format(h1="Formation Data analyst", body="Data 8 semaines 3900 euros. " * 15)},
    {"url": BASE + "/mentions-legales", "depth": 1,
     "html": SAME.format(h1="Mentions légales", body="Éditeur du site. " * 30)},
]


# ── titres distincts ──────────────────────────────────────────────────────────

def test_shared_title_replaced_by_h1():
    prepared = {p["url"]: ("Exemple Academy", "texte") for p in PAGES}
    out = distinct_titles(prepared, {p["url"]: p["html"] for p in PAGES})
    assert out[BASE + "/formations/python"][0] == "Formation Python"
    assert out[BASE + "/formations/data"][0] == "Formation Data analyst"
    assert out[BASE + "/"][0] == "Exemple Academy"          # accueil : titre du site


def test_unique_title_kept():
    prepared = {BASE + "/a": ("Page A", "t"), BASE + "/b": ("Page B", "t")}
    assert distinct_titles(prepared, {})[BASE + "/a"][0] == "Page A"


def test_path_label():
    assert path_label(BASE + "/catalogue/genai-managers") == "Genai managers"


# ── questions « liste » et diversité ─────────────────────────────────────────

@pytest.mark.parametrize("q", ["Quelles sont les formations disponibles ?",
                               "liste des services", "Quels types de cours ?"])
def test_list_queries_detected(q):
    assert is_list_query(q)


def test_specific_question_is_not_list():
    assert not is_list_query("Combien coûte la formation Python ?")


def test_diverse_caps_passages_per_page():
    hits = [{"meta": {"url": "/a"}}] * 5 + [{"meta": {"url": "/b"}}, {"meta": {"url": "/c"}}]
    urls = [h["meta"]["url"] for h in _diverse(hits, k=10, per_page=2)]
    assert urls == ["/a", "/a", "/b", "/c"]


# ── liens « En savoir plus » ─────────────────────────────────────────────────

SITE = [{"title": "Formation Python", "url": BASE + "/formations/python"},
        {"title": "Accueil", "url": BASE + "/"},
        {"title": "Mentions", "url": BASE + "/mentions-legales"}]


def test_cited_links_only_pages_in_reply():
    reply = f"Voir [la page]({BASE}/formations/python/). Accueil : {BASE}/ et {BASE}/mentions-legales"
    assert cited_links(reply, SITE) == [{"title": "Formation Python",
                                         "url": BASE + "/formations/python"}]


def test_cited_links_skip_action_urls_and_unknown():
    reply = f"{BASE}/formations/python et https://autre.fr/page"
    assert cited_links(reply, SITE, exclude_urls=[BASE + "/formations/python"]) == []


# ── /chat de bout en bout ────────────────────────────────────────────────────

@pytest.fixture
def client(temp_store, monkeypatch):
    from app import api_agent, llm
    from app.api_agent import site_map
    from scraper import pipeline
    site_map.reset_cache()
    monkeypatch.setattr(pipeline, "_crawl", lambda url, mp, md, progress: ((PAGES, 0, 4), "test"))
    prompts = []

    def fake_chat(system_prompt, messages):
        prompts.append(system_prompt)
        return f"- **Formation Python** – 12 semaines\nDétails : {BASE}/formations/python"

    monkeypatch.setattr(llm, "chat", fake_chat)
    pipeline.run_pipeline(BASE + "/")
    c = api_agent.app.test_client()
    c.prompts = prompts
    return c


def test_chat_gives_site_map_and_cited_links(client):
    r = client.post("/chat", json={"message": "Quelles sont les formations disponibles ?",
                                   "site_url": BASE})
    data = r.get_json()
    prompt = client.prompts[-1]
    assert "PLAN DU SITE" in prompt
    assert "Formation Data analyst" in prompt          # titre distinct, issu du <h1>
    assert "/mentions-legales" not in prompt.split("PLAN DU SITE (pages")[1]
    assert data["links"] == [{"title": "Formation Python", "url": BASE + "/formations/python"}]
    assert "jamais à la place" in prompt               # contenu d'abord, lien en complément


def test_cited_links_shared_titles_use_url_label():
    pages = [{"title": "Exemple Academy", "url": BASE + "/catalogue/genai-managers"},
             {"title": "Exemple Academy", "url": BASE + "/faq"}]
    reply = f"{BASE}/catalogue/genai-managers et {BASE}/faq"
    assert [l["title"] for l in cited_links(reply, pages)] == ["Genai managers", "Faq"]
