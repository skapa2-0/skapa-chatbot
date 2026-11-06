from app.metadata import init_db, log_scraped_page, get_recent_pages, upsert_site, get_site


def test_init_db_creates_table(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)  # ne doit pas lever d'erreur, meme appele plusieurs fois
    init_db(db_path)


def test_log_and_query_pages(tmp_path):
    db_path = str(tmp_path / "test.db")

    log_scraped_page("https://exemple.com/page1", "Page 1", 3, db_path=db_path)
    log_scraped_page("https://exemple.com/page2", "Page 2", 5, db_path=db_path)

    pages = get_recent_pages(limit=10, db_path=db_path)

    assert len(pages) == 2
    urls = {p["url"] for p in pages}
    assert urls == {"https://exemple.com/page1", "https://exemple.com/page2"}
    assert all("nb_chunks" in p for p in pages)


def test_get_recent_pages_respects_limit(tmp_path):
    db_path = str(tmp_path / "test.db")

    for i in range(5):
        log_scraped_page(f"https://exemple.com/page{i}", f"Page {i}", i, db_path=db_path)

    pages = get_recent_pages(limit=2, db_path=db_path)
    assert len(pages) == 2


# ── sites table ───────────────────────────────────────────────────────────────

def test_upsert_and_get_site(tmp_path):
    db_path = str(tmp_path / "test.db")
    upsert_site("exemple.fr", "#e53e3e", "Exemple", db_path=db_path)
    row = get_site("exemple.fr", db_path=db_path)
    assert row is not None
    assert row["brand_color"] == "#e53e3e"
    assert row["site_title"] == "Exemple"
    assert row["updated_at"]

def test_upsert_site_updates_existing(tmp_path):
    db_path = str(tmp_path / "test.db")
    upsert_site("exemple.fr", "#e53e3e", "Ancien", db_path=db_path)
    upsert_site("exemple.fr", "#2b6cb0", "Nouveau", db_path=db_path)
    row = get_site("exemple.fr", db_path=db_path)
    assert row["brand_color"] == "#2b6cb0"
    assert row["site_title"] == "Nouveau"

def test_upsert_site_accepts_null_color(tmp_path):
    db_path = str(tmp_path / "test.db")
    upsert_site("exemple.fr", None, "Exemple", db_path=db_path)
    row = get_site("exemple.fr", db_path=db_path)
    assert row["brand_color"] is None

def test_get_site_returns_none_for_unknown(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    assert get_site("inconnu.fr", db_path=db_path) is None

def test_upsert_site_stores_actions(tmp_path):
    db_path = str(tmp_path / "test.db")
    actions = [{"label": "Candidater", "url": "https://exemple.fr/candidater"}]
    upsert_site("exemple.fr", "#e53e3e", "Exemple", actions=actions, db_path=db_path)
    row = get_site("exemple.fr", db_path=db_path)
    assert row["actions"] == actions

def test_upsert_site_actions_none_by_default(tmp_path):
    db_path = str(tmp_path / "test.db")
    upsert_site("exemple.fr", "#e53e3e", "Exemple", db_path=db_path)
    row = get_site("exemple.fr", db_path=db_path)
    assert row["actions"] is None
