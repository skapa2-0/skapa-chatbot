"""Accélérations : pas de ré-embedding inutile, indexation progressive."""

from scraper.parser import parse_page

HTML = "<title>T</title><main><p>{}</p></main>"


class CountingEmbedding:
    def __init__(self, inner):
        self.inner, self.n = inner, 0

    def __call__(self, input):
        self.n += len(input)
        return self.inner(input)


def _store(monkeypatch, temp_store):
    from app import chroma_client
    from conftest import FakeEmbedding
    emb = CountingEmbedding(FakeEmbedding())
    monkeypatch.setattr(chroma_client, "_resolve_embedding", lambda: (emb, "test:count"))
    chroma_client.reset_for_tests()
    return emb


def test_unchanged_chunks_are_not_reembedded(temp_store, monkeypatch):
    from scraper.ingest import replace_domain_chunks
    emb = _store(monkeypatch, temp_store)
    a = parse_page("https://s.fr/a", HTML.format("Texte A stable."))
    b = parse_page("https://s.fr/b", HTML.format("Texte B version 1."))
    replace_domain_chunks("s.fr", a + b)
    assert emb.n == 2
    b2 = parse_page("https://s.fr/b", HTML.format("Texte B version 2."))
    replace_domain_chunks("s.fr", parse_page("https://s.fr/a", HTML.format("Texte A stable.")) + b2)
    assert emb.n == 3                      # seul B (modifié) est recalculé


def test_early_indexer_makes_first_pages_searchable(temp_store, monkeypatch):
    from scraper.ingest import count_domain
    from scraper.pipeline.early import EarlyIndexer
    _store(monkeypatch, temp_store)
    ready = []
    early = EarlyIndexer(on_ready=lambda: ready.append(True), n=3)
    for i in range(5):
        early.add({"url": f"https://s.fr/{i}", "depth": 1, "html": HTML.format(f"Page numéro {i}.")})
    early.wait()
    assert ready == [True]
    assert count_domain("s.fr") == 3       # les 3 premières pages, avant la fin du crawl
