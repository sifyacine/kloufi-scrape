import asyncio
import json
import os
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from bs4 import BeautifulSoup
from .scrape_details import extract_property_details

# ===================== OUTPUT CONFIG =====================
OUTPUT_DIR = "immobilier/krello"
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "krello_properties.json")

all_urls = set()
all_properties = []

# ===================== LISTINGS SCRAPER =====================
async def scrape_all_listings():
    global all_urls

    url = "https://krello.net/fr?type=explorer"

    # JS: scroll-driven pagination + optional button click
    js_load_all = """
    (async () => {
        console.log("🚀 Krello scroll loader started");

        let lastCount = 0;
        let stableRounds = 0;
        const maxRounds = 60;

        for (let round = 0; round < maxRounds; round++) {

            // Force scroll (triggers Krello pagination)
            window.scrollTo(0, document.body.scrollHeight);
            await new Promise(r => setTimeout(r, 1500));

            // Try clicking "Afficher plus" if present
            let btn =
                document.querySelector('button[aria-label*="Afficher"]') ||
                Array.from(document.querySelectorAll('button'))
                    .find(b => b.textContent.includes("Afficher"));

            if (btn && !btn.disabled && btn.offsetParent !== null) {
                btn.scrollIntoView({ block: "center" });
                await new Promise(r => setTimeout(r, 300));
                btn.click();
                console.log("🖱️ Clicked load more");
            }

            // Wait for DOM updates
            await new Promise(r => setTimeout(r, 2000));

            const count = document.querySelectorAll("article").length;
            console.log(`📊 Articles loaded: ${count}`);

            if (count === lastCount) {
                stableRounds++;
                console.log(`⚠️ No new articles (${stableRounds}/3)`);
            } else {
                stableRounds = 0;
            }

            lastCount = count;

            // Stop only after repeated stability
            if (stableRounds >= 3) {
                console.log("✅ All listings fully loaded");
                break;
            }
        }

        console.log("⏹️ Loader finished");
    })();
    """

    browser_config = BrowserConfig(
        headless=True,  # keep false for testing
        browser_type="chromium",
        text_mode=False,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        print("🚀 Opening browser and loading all Krello listings...\n")

        result = await crawler.arun(
            url=url,
            config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                js_code=[js_load_all],
                delay_before_return_html=90,
                page_timeout=120_000,  # allow long JS execution
            )
        )

        if not result.success:
            print(f"❌ Crawl failed: {result.error_message}")
            return

        print("\n✅ HTML captured. Parsing listings...\n")

        soup = BeautifulSoup(result.html, "html.parser")
        articles = soup.find_all("article")
        print(f"📊 Total articles found: {len(articles)}\n")

        for article in articles:
            a_tag = article.find("a", href=True)
            if a_tag and a_tag["href"].startswith("/listing-details/"):
                full_url = "https://krello.net/fr" + a_tag["href"]
                all_urls.add(full_url)

        print(f"🔗 Unique property URLs collected: {len(all_urls)}\n")

# ===================== DETAILS SCRAPER =====================
async def main():
    await scrape_all_listings()

    if not all_urls:
        print("❌ No URLs found. Stopping.")
        return

    print("=" * 80)
    print(f"📥 Extracting details from {len(all_urls)} properties...")
    print("=" * 80 + "\n")

    success_count = 0

    for i, url in enumerate(sorted(all_urls), 1):
        print(f"[{i}/{len(all_urls)}] {url}")
        try:
            details = await extract_property_details(url)
            if details:
                all_properties.append(details)
                success_count += 1
        except Exception as e:
            print(f"   ❌ Error: {e}")

    # with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    #     json.dump(all_properties, f, ensure_ascii=False, indent=4)



# ===================== ENTRY POINT =====================
if __name__ == "__main__":
    asyncio.run(main())
