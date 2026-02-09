import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import tldextract
from scraper.proxy.proxy_sources import fetch_proxies
from scraper.proxy.proxy_manager import ProxyManager
from scraper.crawler.crawler_runner import crawl
from scraper.browser.fingerprint import build_context

async def main():
    urls = ["https://www.ouedkniss.com/immobilier/1"]
    proxies = await fetch_proxies()
    manager = ProxyManager(proxies)

    for url in urls:
        domain = tldextract.extract(url).top_domain_under_public_suffix
        proxy = manager.get_proxy(domain)
        try:
            html = await crawl(url, proxy, build_context())
            print(html)
            print("SUCCESS", url)
        except Exception as e:
            print(f"FAILED {url}: {e}")
            manager.rotate(domain)

asyncio.run(main())