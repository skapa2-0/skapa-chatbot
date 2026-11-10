"""Tests pour les routes admin et la conformité RGPD."""
import sqlite3

import pytest


@pytest.fixture
def client(temp_store, monkeypatch):
    from app import api_agent, config
    monkeypatch.setattr(config, "ADMIN_TOKEN", "test-token")
    monkeypatch.setattr(config, "SCRAPE_PUBLIC", False)
    api_agent.app.config["TESTING"] = True
    return api_agent.app.test_client()


AUTH = {"Authorization": "Bearer test-token"}


# ── Contrôle d'accès ──────────────────────────────────────────────────────────

def test_stats_requires_auth(client):
    r = client.get("/api/stats?domain=test.fr")
    assert r.status_code == 401


def test_sites_requires_auth(client):
    r = client.get("/api/sites")
    assert r.status_code == 401


# ── Validation des routes publiques ───────────────────────────────────────────

def test_feedback_rejects_invalid_vote(client):
    r = client.post("/api/feedback", json={"domain": "test.fr", "vote": "meh"})
    assert r.status_code == 400


def test_feedback_rejects_missing_domain(client):
    r = client.post("/api/feedback", json={"vote": "up"})
    assert r.status_code == 400


def test_feedback_accepts_valid_votes(client):
    for vote in ("up", "down"):
        r = client.post("/api/feedback", json={"domain": "test.fr", "vote": vote})
        assert r.status_code == 200, f"vote={vote} refusé"


def test_click_rejects_missing_fields(client):
    assert client.post("/api/click", json={"domain": "test.fr"}).status_code == 400
    assert client.post("/api/click", json={"action": "Candidater"}).status_code == 400


# ── RGPD : aucune colonne ne stocke le texte des questions ───────────────────

def test_no_question_text_column(tmp_path):
    from app.metadata import init_db
    db = str(tmp_path / "test.db")
    init_db(db)
    conn = sqlite3.connect(db)
    forbidden = {"question", "text", "message", "content", "query"}
    for table in ("feedback", "clicks", "chat_requests"):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        assert not (cols & forbidden), \
            f"table '{table}' contient une colonne interdite : {cols & forbidden}"


# ── Totaux corrects sur un jeu de données de référence ───────────────────────

def test_stats_returns_correct_totals(tmp_path):
    from app import chat_stats, metadata
    db = str(tmp_path / "test.db")

    metadata.add_feedback("x.fr", "up", db_path=db)
    metadata.add_feedback("x.fr", "up", db_path=db)
    metadata.add_feedback("x.fr", "down", db_path=db)
    metadata.log_chat_request("x.fr", 500, False, db_path=db)
    metadata.log_chat_request("x.fr", 1500, False, db_path=db)
    metadata.log_chat_request("x.fr", 300, True, db_path=db)
    metadata.add_click("x.fr", "Candidater", db_path=db)
    metadata.add_click("x.fr", "Candidater", db_path=db)
    metadata.add_click("x.fr", "Contact", db_path=db)

    s = chat_stats.get_stats("x.fr", 7, db_path=db)
    assert s["total_questions"] == 3
    assert abs(s["error_rate"] - 1 / 3) < 0.01
    assert abs(s["satisfaction"] - 2 / 3) < 0.01
    assert s["total_clicks"] == 3
    assert s["clicks_by_action"][0] == {"action": "Candidater", "count": 2}
