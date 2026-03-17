import json
import re
import sys
from typing import Any, Optional
from urllib.parse import urljoin

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_URL = "https://ekantipur.com"


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def _abs_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return urljoin(BASE_URL, url)


def _safe_attr(el, name: str) -> Optional[str]:
    try:
        return el.get_attribute(name)
    except Exception:
        return None


def _safe_text(el) -> Optional[str]:
    try:
        return _clean_text(el.text_content())
    except Exception:
        return None


def _first_attr(el, names: list[str]) -> Optional[str]:
    for n in names:
        v = _safe_attr(el, n)
        if v:
            return v
    return None


def _meta_content(page, selector: str) -> Optional[str]:
    try:
        return page.locator(selector).first.get_attribute("content")
    except Exception:
        return None


def _extract_article_details(page, url: str) -> dict[str, Optional[str]]:
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    category = (
        _clean_text(_meta_content(page, 'meta[property="article:section"]'))
        or _clean_text(_meta_content(page, 'meta[name="section"]'))
        or _clean_text(page.locator("nav[aria-label*='breadcrumb'] a").last.text_content() if page.locator("nav[aria-label*='breadcrumb'] a").count() else None)
    )

    author = (
        _clean_text(_meta_content(page, 'meta[name="author"]'))
        or _clean_text(_meta_content(page, 'meta[property="article:author"]'))
        or _clean_text(page.locator('a[rel="author"]').first.text_content() if page.locator('a[rel="author"]').count() else None)
        or _clean_text(page.locator("[class*='author'], [class*='byline']").first.text_content() if page.locator("[class*='author'], [class*='byline']").count() else None)
    )

    image_url = _clean_text(_meta_content(page, 'meta[property="og:image"]'))
    return {"category": category, "author": author, "image_url": image_url}


def extract_entertainment_news(page) -> list[dict[str, Any]]:
    # Navigate directly to the Entertainment section (equivalent to clicking the nav item).
    page.goto(f"{BASE_URL}/entertainment", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    # Page structure (as of 2026-03): repeated blocks under `.category-main-wrapper`.
    cards = page.locator(".category-main-wrapper .category-wrapper > .category")
    cards.first.wait_for(timeout=30_000)

    category = "मनोरञ्जन"
    try:
        header_category = _clean_text(page.locator("header .category-name a").first.text_content())
        if header_category:
            category = header_category
    except Exception:
        pass

    results: list[dict[str, Any]] = []
    for i in range(min(5, cards.count())):
        card = cards.nth(i)

        title_el = card.locator(".category-description h2 a").first
        title = None
        href = None
        try:
            title = _clean_text(title_el.text_content())
            href = title_el.get_attribute("href")
        except Exception:
            title = None
            href = None

        if not title or not href:
            continue

        summary = None
        summary_el = card.locator(".category-description > p").first
        try:
            if summary_el.count():
                summary = _clean_text(summary_el.text_content())
        except Exception:
            summary = None

        # Images can be eager (`src`) or lazy (`data-src`).
        img_el = card.locator(".category-image img").first
        image_url = None
        try:
            image_url = img_el.get_attribute("src") or img_el.get_attribute("data-src")
        except Exception:
            image_url = None

        author = None
        author_el = card.locator(".author-name a").first
        try:
            if author_el.count():
                author = _clean_text(author_el.text_content())
        except Exception:
            author = None

        results.append(
            {
                "title": title,
                "image_url": _abs_url(image_url),
                "category": category,
                "author": author,
                "summary": summary,
            }
        )

    return results


def extract_cartoon_of_the_day(page) -> dict[str, Any]:
    page.goto(f"{BASE_URL}/cartoon", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    # The cartoon listing uses an image-link (often directly to the CDN thumb URL) and
    # the caption is plain text like "गजब छ बा! - अविन" (not necessarily an <a href>).
    extracted: dict[str, Optional[str]] = page.evaluate(
        """() => {
          const imageLink =
            document.querySelector("a[href*='assets-cdn-api.ekantipur.com/thumb.php']") ||
            document.querySelector("a[href*='thumb.php?src=']");
          if (!imageLink) return { title: null, author: null, date: null, image_url: null };

          // Find the nearest card-ish container that also contains caption text.
          let card = imageLink.parentElement;
          for (let i = 0; i < 10 && card; i++) {
            const caption = card.querySelector("p");
            if (caption && (caption.textContent || "").includes("-")) break;
            card = card.parentElement;
          }

          const textCandidates = card
            ? Array.from(card.querySelectorAll("p, span, div"))
                .map(n => (n.textContent || "").replace(/\\s+/g, " ").trim())
                .filter(Boolean)
            : [];
          const titleAuthor =
            textCandidates.find(t => (t.includes("-") || t.includes("–")) && !/[०-९]/.test(t)) ||
            textCandidates.find(t => t.includes("-") || t.includes("–")) ||
            null;
          // Date on the listing is Nepali numerals, e.g. "चैत्र ३, २०८२".
          const date =
            textCandidates.find(t => /[०-९]/.test(t) && t.includes(",") && !(t.includes("-") || t.includes("–"))) ||
            textCandidates.find(t => /[०-९]/.test(t) && /[०-९]{4}/.test(t) && !(t.includes("-") || t.includes("–"))) ||
            null;
          let title = null, author = null;
          if (titleAuthor) {
            const parts = titleAuthor.split(/\\s*[-–]\\s*/);
            if (parts.length >= 2) {
              title = parts[0].trim() || null;
              author = parts.slice(1).join(" - ").trim() || null;
            } else {
              title = titleAuthor.trim() || null;
            }
          }

          return { title, author, date, image_url: imageLink.href || null };
        }"""
    )

    return {
        "title": _clean_text(extracted.get("title")),
        "image_url": _abs_url(_clean_text(extracted.get("image_url"))),
        "author": _clean_text(extracted.get("author")),
        "date": _clean_text(extracted.get("date")),
    }


def main() -> None:
    # Prevent Windows console UnicodeEncodeError if anything logs Nepali text.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    data: dict[str, Any] = {"entertainment_news": [], "cartoon_of_the_day": {}}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ne-NP")
        page = context.new_page()
        page.set_default_timeout(30_000)

        try:
            data["entertainment_news"] = extract_entertainment_news(page)
        except PlaywrightTimeoutError:
            data["entertainment_news"] = []
        except Exception:
            data["entertainment_news"] = []

        try:
            data["cartoon_of_the_day"] = extract_cartoon_of_the_day(page)
        except PlaywrightTimeoutError:
            data["cartoon_of_the_day"] = {"title": None, "image_url": None, "author": None}
        except Exception:
            data["cartoon_of_the_day"] = {"title": None, "image_url": None, "author": None}

        context.close()
        browser.close()

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

