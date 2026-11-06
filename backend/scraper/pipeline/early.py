"""Indexation progressive : les premières pages sont indexées pendant que le
crawl continue, pour que le chat puisse répondre au bout de quelques secondes.

Les chunks « précoces » sont seulement ajoutés (jamais de suppression) ; à la fin,
replace_domain_chunks() remet l'index au propre avec toutes les pages.
"""

import threading

from app import config
from scraper.ingest import ingest_chunks
from scraper.parser import parse_page

EARLY_PAGES = config.env_int("SCRAPER_EARLY_PAGES", 10)


class EarlyIndexer:
    def __init__(self, on_ready=None, n=EARLY_PAGES):
        self.n, self.on_ready = n, on_ready
        self.pages, self.thread = [], None

    def add(self, page):
        """Appelé par le crawler pour chaque page récupérée."""
        if page is None or self.thread is not None or self.n <= 0:
            return
        self.pages.append(page)
        if len(self.pages) >= self.n:
            self.thread = threading.Thread(target=self._index, args=(list(self.pages),),
                                           name="early-index", daemon=True)
            self.thread.start()

    def _index(self, pages):
        try:
            chunks = []
            for p in pages:
                if p.get("format") == "pdf":
                    chunks += parse_page(p["url"], None, depth=p["depth"],
                                         text=p["text"], title=p.get("title", ""))
                else:
                    chunks += parse_page(p["url"], p["html"], depth=p["depth"])
            ingest_chunks(chunks)
            print(f"[early] {len(pages)} pages indexées, le chat peut répondre")
            if self.on_ready:
                self.on_ready()
        except Exception as exc:  # l'index final sera fait de toute façon
            print(f"[early] indexation anticipée échouée : {exc}")

    def wait(self):
        """À appeler avant l'indexation finale (un seul écrivain à la fois)."""
        if self.thread is not None:
            self.thread.join()
