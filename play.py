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
        if start and end:
             print(f"✅ Applying date filter from {start.isoformat()} to {end.isoformat()}")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=True
        )
        page = await context.new_page()
        await page.goto(INBOX_URL, timeout=60000)

        # --- Sort by "Recent" before scraping ---
        try:
            sort_dropdown_selector = "select.sort-lAhhIt"
            await page.wait_for_selector(sort_dropdown_selector, timeout=15000)
            await page.select_option(sort_dropdown_selector, "recent")
            await page.wait_for_load_state("networkidle", timeout=15000)
            print("✅ Sorted inbox by 'Recent'.")
        except PlaywrightTimeoutError:
            print("⚠️  Sort dropdown not found. Proceeding with default sort order.")

        try:
            await page.wait_for_selector("div.reader2-post-container", timeout=30000)
        except PlaywrightTimeoutError:
            print("❌ Could not find post containers. You might need to log in.")
            await context.close()
            return []

        results = []
        processed_urls = set()
        
        # --- Loop to handle infinite scrolling ---
        while True:
            containers = page.locator("div.reader2-post-container")
            current_count = await containers.count()

            for i in range(current_count):
                el = containers.nth(i)
                href_element = el.locator("a.linkRowA-pQXF7n")
                if await href_element.count() == 0:
                    continue # Skip if the main link is missing
                
                href = (await href_element.get_attribute("href")) or ""
                if not href or href in processed_urls:
                    continue

                full_url = urljoin(BASE_URL, href)
                processed_urls.add(href)

                title = (await el.locator("div.reader2-post-title").text_content() or "").strip()
                date_raw = (await el.locator("div.inbox-item-timestamp").text_content() or "").strip()
                name = (await el.locator("div.pub-name a").text_content() or "N/A").strip()
                
                if not title:
                    continue

                art_date = None
                low = date_raw.lower()
                if ":" in date_raw and ("am" in low or "pm" in low):
                    art_date = today
                elif "yesterday" in low:
                    art_date = today - timedelta(days=1)
                else:
                    art_date = parse_webpage_date_string(date_raw, year, today)

                if use_filter:
                    if not art_date:
                        continue
                    if not (start <= art_date <= end):
                        continue
                
                results.append({
                    "parsed_article_date": art_date, # Store the date object itself
                    "substack_name":       name,
                    "title":               title,
                    "url":                 full_url
                })

            # Check the date of the last processed article to see if we should stop scrolling
            last_container = containers.nth(-1)
            last_date_raw = (await last_container.locator("div.inbox-item-timestamp").text_content() or "").strip()
            last_art_date = parse_webpage_date_string(last_date_raw, year, today)

            if use_filter and last_art_date and start and last_art_date < start:
                print(f"✅ Stopped scrolling as last article date ({last_art_date}) is older than filter start date ({start}).")
                break

            # Scroll down to load more content
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            # Wait a moment for new content to load
            await page.wait_for_timeout(2000) 

            new_count = await containers.count()
            if new_count == current_count:
                print("✅ Reached end of inbox, no new articles loaded.")
                break # Break if no new articles were loaded after scrolling
        # --- End of scrolling loop ---

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
        # NEW: Sort results by date ascending (oldest first) before saving
        articles.sort(key=lambda x: x.get('parsed_article_date') or datetime.min.date(), reverse=False)
        for a in articles:
            # NEW: Format date to dd-mm-yyyy, handle if date is None
            date_obj = a['parsed_article_date']
            date_str = date_obj.strftime('%d-%m-%Y') if date_obj else "N/A"

            f.write(f"Date:     {date_str}\n")
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
        print("⚠️  No articles found or login might be needed.")
