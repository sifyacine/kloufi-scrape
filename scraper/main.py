import asyncio
import tldextract
from proxy.proxy_sources import fetch_proxies
from proxy.proxy_manager import ProxyManager
from crawler.crawler_runner import crawl
from browser.fingerprint import build_context

async def main():
    urls = ["https://www.ouedkniss.com/terrain-vente-alger-birkhadem-algerie-d48585919"]
    proxies = await fetch_proxies()
    manager = ProxyManager(proxies)

    for url in urls:
        domain = tldextract.extract(url).top_domain_under_public_suffix
        proxy = manager.get_proxy(domain)
        try:
            html = await crawl(url, proxy, build_context())
            print("SUCCESS", url)
        except Exception as e:
            print(f"FAILED {url}: {e}")
            manager.rotate(domain)

asyncio.run(main())