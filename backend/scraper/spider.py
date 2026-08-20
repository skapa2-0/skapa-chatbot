"""
scraper/spider.py
------------------
Solution de repli (ou complément) si l'API Supabase n'est pas accessible
directement. Utilise un vrai navigateur Chromium pour :
  1. Découvrir toutes les URLs internes du site (crawl BFS depuis la home).
  2. Ouvrir chaque page, attendre le chargement réseau complet.
  3. Scroller automatiquement jusqu'en bas (déclenche le lazy loading).
  4. Cliquer sur tous les accordéons / "voir plus" / "en savoir plus".
  5. Extraire uniquement le contenu utile (pas nav/footer/cookies).
  6. Sauvegarder un JSON par page dans data/pages/.

Usage (depuis /opt/chatbot/backend) :
    playwright install chromium   # une seule fois
    python -m scraper.spider --base-url https://skapa-academy.com

Ou directement depuis ce dossier :
    python spider.py --base-url https://skapa-academy.com
"""

import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Page

OUT_DIR = Path("data/pages")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Sélecteurs de contenu à exclure de l'extraction (nav, footer, cookies, etc.)
NOISE_SELECTORS = [
    "nav", "footer", "header",
    "[class*='cookie']", "[id*='cookie']",
    "[class*='navbar']", "[class*='footer']",
    "script", "style", "noscript", "svg",
]

# Textes de boutons déclenchant du contenu caché (accordéons, "voir plus", etc.)
EXPAND_TEXT_PATTERNS = [
    "voir plus", "en savoir plus", "afficher", "détails", "lire la suite",
    "voir le programme", "voir la formation", "développer", "plus d'infos",
]


async def autoscroll(page: Page, step: int = 600, pause_ms: int = 250, max_steps: int = 60):
    """Scrolle progressivement jusqu'en bas pour déclencher le lazy loading."""
    prev_height = 0
    for _ in range(max_steps):
        height = await page.evaluate("document.body.scrollHeight")
        if height == prev_height:
            break
        prev_height = height
        await page.mouse.wheel(0, step)
        await page.wait_for_timeout(pause_ms)
    await page.wait_for_timeout(500)


async def expand_hidden_content(page: Page):
    """Ouvre accordéons et boutons 'voir plus' détectés par texte ou aria-expanded.

    Important : on ne prend PAS un snapshot des éléments puis on boucle par index,
    car cliquer sur un accordéon fait passer son aria-expanded à 'true', ce qui le
    retire du sélecteur [aria-expanded='false'] et DÉCALE les index suivants — un
    accordéon sur deux serait alors sauté. On refait donc la requête à chaque passe
    et on s'arrête quand plus aucun élément fermé n'est trouvé (plusieurs passes
    gèrent aussi les accordéons imbriqués qui n'apparaissent qu'une fois le parent ouvert).
    """
    for _ in range(15):
        handles = await page.query_selector_all("[aria-expanded='false']")
        if not handles:
            break
        clicked_any = False
        for handle in handles:
            try:
                if await handle.is_visible():
                    await handle.click(timeout=2000)
                    clicked_any = True
                    await page.wait_for_timeout(150)
            except Exception:
                pass
        if not clicked_any:
            break

    # 2. Boutons/liens contenant un texte typique de contenu caché.
    # element_handles() fige la liste (contrairement à .nth() sur un Locator
    # dynamique), donc pas de décalage d'index même si le DOM change entre les clics.
    for pattern in EXPAND_TEXT_PATTERNS:
        try:
            buttons = page.get_by_text(re.compile(pattern, re.IGNORECASE))
            handles = await buttons.element_handles()
            for handle in handles[:20]:
                try:
                    if await handle.is_visible():
                        await handle.click(timeout=1500)
                        await page.wait_for_timeout(200)
                except Exception:
                    pass
        except Exception:
            pass


async def extract_clean_text(page: Page) -> str:
    """Extrait le texte visible en excluant nav/footer/scripts."""
    text = await page.evaluate(
        """(noiseSelectors) => {
            const clone = document.body.cloneNode(true);
            noiseSelectors.forEach(sel => {
                clone.querySelectorAll(sel).forEach(el => el.remove());
            });
            return clone.innerText;
        }""",
        NOISE_SELECTORS,
    )
    # Nettoyage : lignes vides multiples, espaces
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    return "\n".join(lines)


async def discover_links(page: Page, base_url: str) -> set[str]:
    hrefs = await page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href'))"
    )
    domain = urlparse(base_url).netloc
    found = set()
    for h in hrefs:
        if not h or h.startswith("#") or h.startswith("mailto:") or h.startswith("tel:"):
            continue
        full = urljoin(base_url, h)
        parsed = urlparse(full)
        if parsed.netloc == domain:
            clean = parsed._replace(query="", fragment="").geturl()
            found.add(clean.rstrip("/"))
    return found


async def scrape_page(context, url: str) -> dict:
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=45000)
    except Exception:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)

    await autoscroll(page)
    await expand_hidden_content(page)
    await autoscroll(page)  # re-scroll au cas où l'expansion a ajouté du contenu

    title = await page.title()
    content = await extract_clean_text(page)
    links = await discover_links(page, url)

    await page.close()
    return {"url": url, "title": title, "content": content, "links": list(links)}


async def crawl(base_url: str, max_pages: int = 200):
    visited: set[str] = set()
    queue = [base_url.rstrip("/")]
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        )

        while queue and len(visited) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            print(f"→ Scraping: {url}")

            try:
                data = await scrape_page(context, url)
            except Exception as e:
                print(f"  ⚠️  Erreur sur {url}: {e}")
                continue

            results.append(data)

            slug = re.sub(r"[^a-zA-Z0-9]+", "_", urlparse(url).path).strip("_") or "home"
            out_path = OUT_DIR / f"{slug}.json"
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            for link in data["links"]:
                if link not in visited and link not in queue:
                    queue.append(link)

        await browser.close()

    print(f"\n✅ {len(results)} pages scrapées → {OUT_DIR}/")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://skapa-academy.com")
    parser.add_argument("--max-pages", type=int, default=200)
    args = parser.parse_args()

    asyncio.run(crawl(args.base_url, args.max_pages))


if __name__ == "__main__":
    main()