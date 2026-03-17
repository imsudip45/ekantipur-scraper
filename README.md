## ekantipur-scraper

Playwright (Python) scraper for `ekantipur.com` that extracts:

- Top 5 Entertainment (मनोरञ्जन) news cards
- Cartoon of the Day (latest item from the cartoon listing)

### Setup

Install dependencies and Playwright browser:

```bash
uv sync
uv run playwright install chromium
```

### Run

```bash
uv run python scraper.py
```

This will generate `output.json` in the project root.

