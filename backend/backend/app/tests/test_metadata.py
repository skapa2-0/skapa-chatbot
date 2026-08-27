from app.metadata import init_db, log_scraped_page, get_recent_pages


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
