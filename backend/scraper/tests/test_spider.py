from scraper import spider
from scraper.spider import domain_key, extract_links, is_crawlable, normalize_url, same_domain


def test_domain_key_ignores_www_case_and_port():
    assert domain_key("https://WWW.Skapa-Academy.fr:443/a") == "skapa-academy.fr"
    assert domain_key("skapa-academy.fr") == "skapa-academy.fr"


def test_same_domain_with_and_without_www():
    # Bug d'origine : skapa-academy.fr redirige vers www. -> tous les liens rejetés
    assert same_domain("https://skapa-academy.fr", "https://www.skapa-academy.fr/formations")


def test_normalize_url():
    assert normalize_url("https://Site.fr") == "https://site.fr/"
    assert normalize_url("https://site.fr/a/#x") == "https://site.fr/a"
    assert normalize_url("https://site.fr/a?utm_source=x&b=2&a=1") == "https://site.fr/a?a=1&b=2"


def test_is_crawlable_skips_files_and_admin():
    assert is_crawlable("https://site.fr/formations")
    assert not is_crawlable("https://site.fr/brochure.pdf")
    assert not is_crawlable("https://site.fr/wp-admin/x")
    assert not is_crawlable("mailto:a@b.fr")


def test_extract_links_keeps_internal_pages_only():
    html = """
      <a href="/formations/">F</a> <a href="https://www.site.fr/tarifs#prix">T</a>
      <a href="https://autre.com/x">ext</a> <a href="/doc.pdf">pdf</a>
      <a href="mailto:x@site.fr">m</a> <a href="#top">top</a>
    """
    links = extract_links(html, "https://site.fr/")
    assert links == {"https://site.fr/formations", "https://www.site.fr/tarifs"}


def test_crawl_follows_redirect_to_www(monkeypatch):
    pages = {
        "https://www.site.fr/": '<a href="https://www.site.fr/a">a</a>',
        "https://www.site.fr/a": "<p>page a</p>",
    }

    class Resp:
        def __init__(self, url):
            self.url = "https://www.site.fr/" if url == "https://site.fr/" else url
            self.status_code = 200 if self.url in pages else 404
            self.text = pages.get(self.url, "")
            self.headers = {"Content-Type": "text/html; charset=utf-8"}
            self.encoding = "utf-8"

        def raise_for_status(self):
            if self.status_code >= 400:
                raise spider.requests.HTTPError(self.status_code)

    class FakeSession:
        def __init__(self):
            self.headers = {}

        def get(self, url, **kw):
            return Resp(url)

    monkeypatch.setattr(spider.requests, "Session", FakeSession)
    monkeypatch.setattr(spider, "Robots", lambda url: type("R", (), {"allowed": lambda s, u: True, "sitemaps": []})())
    monkeypatch.setattr(spider, "discover_sitemap_urls", lambda *a, **k: set())
    monkeypatch.setattr(spider, "DELAY_SECONDS", 0)

    got, failed, _ = spider.crawl("https://site.fr", max_pages=10, max_depth=2)
    assert [p["url"] for p in got] == ["https://www.site.fr/", "https://www.site.fr/a"]
    assert failed == 0
