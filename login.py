# login.py
import asyncio
import os
from playwright.async_api import async_playwright

PROFILE_DIR = "data/chrome_profile"
os.makedirs(PROFILE_DIR, exist_ok=True)

async def run_login():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(PROFILE_DIR, headless=False)
        page = await context.new_page()
        await page.goto("https://substack.com/inbox")
        print("\n➡️ Please log in to Substack in the opened browser window.")
        input("After login and your inbox is visible, press ENTER here to finish…\n")
        await context.close()

if __name__ == "__main__":
    asyncio.run(run_login())
