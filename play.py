# play.py - Substack inbox scraper using persistent Chromium profile
import asyncio
import os
from urllib.parse import urljoin
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

PROFILE_DIR = "data/chrome_profile"
INBOX_URL = "https://substack.com/inbox"
BASE_URL = "https://substack.com"
DATE_FILE = os.path.join("data", "date.txt")

os.makedirs(PROFILE_DIR, exist_ok=True)

def load_date_filter():
    """Load date filter from file if present, else return None."""
    if os.path.exists(DATE_FILE):
        val = open(DATE_FILE).read().strip()
        return val or None
    return None

def parse_mm_dd_string(date_mmdd: str, year: int):
    try:
        dt = datetime.strptime(date_mmdd, "%m-%d")
        return dt.replace(year=year).date()
    except:
        return None

def parse_webpage_date_string(raw: str, yr: int, today):
    fmts = [
        "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y",
        "%b %d", "%B %d", "%m-%d"
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(raw, fmt)
            if "%Y" not in fmt:
                dt = dt.replace(year=yr)
                # handle potential year wrap
                if dt.month > today.month + 6:
                    dt = dt.replace(year=yr - 1)
            return dt.date()
        except:
            continue
    return None

async def _scrape(date_filter: str):
    today = datetime.now().date()
    year = today.year

    # Compute date filter range if provided
    start = end = None
    use_filter = bool(date_filter)
    if use_filter:
        q = date_filter.strip().upper()
        import re
        m = re.match(r"LAST (\d+) DAYS", q)
        if m:
            n = int(m.group(1))
            start, end = today - timedelta(days=n - 1), today
        else:
            parts = re.match(r"(.+?) TO (.+)", q)
            if parts:
                start = parse_mm_dd_string(parts.group(1), year)
                end   = parse_mm_dd_string(parts.group(2), year)
            else:
                d = parse_mm_dd_string(q, year)
                start = end = d

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=True
        )
        page = await context.new_page()
        await page.goto(INBOX_URL, timeout=60000)
        try:
            await page.wait_for_selector("div.reader2-post-container", timeout=30000)
        except PlaywrightTimeoutError:
            await context.close()
            return []

        containers = page.locator("div.reader2-post-container")
        count = await containers.count()
        results = []
        for i in range(count):
            el = containers.nth(i)
            href = (await el.locator("a.linkRowA-pQXF7n").get_attribute("href")) or ""
            title = (await el.locator("div.reader2-post-title").text_content() or "").strip()
            date_raw = (await el.locator("div.inbox-item-timestamp").text_content() or "").strip()
            name = (await el.locator("div.pub-name a").text_content() or "N/A").strip()
            if not href or not title:
                continue

            # parse actual date
            art_date = None
            low = date_raw.lower()
            if ":" in date_raw and ("am" in low or "pm" in low):
                art_date = today
            elif "yesterday" in low:
                art_date = today - timedelta(days=1)
            else:
                art_date = parse_webpage_date_string(date_raw, year, today)

            # apply the date filter if requested
            if use_filter:
                if not art_date:
                    continue
                if not (start <= art_date <= end):
                    continue

            full_url = urljoin(BASE_URL, href)
            results.append({
                "parsed_article_date": art_date.isoformat() if art_date else "",
                "substack_name":       name,
                "title":               title,
                "url":                 full_url
            })

        await context.close()
        return results

def scrape_and_save():
    df  = load_date_filter() or ""

    articles = asyncio.run(_scrape(df))
    if not articles:
        return None

    os.makedirs("data", exist_ok=True)
    fname = f"data/UR_{datetime.now().strftime('%Y%m%d-%H%M')}.txt"
    with open(fname, "w", encoding="utf-8") as f:
        for a in articles:
            f.write(f"Date:     {a['parsed_article_date']}\n")
            f.write(f"Substack: {a['substack_name']}\n")
            f.write(f"Title:    {a['title']}\n")
            f.write(f"URL:      {a['url']}\n")
            f.write("\n")
    return fname


# For CLI testing:
if __name__ == "__main__":
    path = scrape_and_save()
    if path:
        print(f"✅ Saved inbox to {path}")
    else:
        print("⚠️  No articles or login needed.")
