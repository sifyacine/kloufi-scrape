import random
from collections import defaultdict
from .proxy_scoring import ProxyScore

class ProxyManager:
    def __init__(self, proxies):
        self.proxies = proxies
        self.scorer = ProxyScore()
        self.domain_proxy = defaultdict(str)

    def get_proxy(self, domain, rotate=False):
        if not rotate and self.domain_proxy[domain]:
            return self.domain_proxy[domain]

        ranked = sorted(self.proxies, key=lambda p: self.scorer.score(p), reverse=True)
        if not ranked:
            raise ValueError("No proxies available to choose from.")
        
        # If rotating, pick random from top 20 to avoid hotspots
        # If not rotating (first time), pick best one
        if rotate:
            top_n = ranked[:20]
            proxy = random.choice(top_n)
        else:
            proxy = ranked[0]
            
        self.domain_proxy[domain] = proxy
        return proxy

    def rotate(self, domain):
        self.domain_proxy[domain] = ""

    def report_success(self, proxy, latency=1.0):
        self.scorer.record(proxy, success=True, latency=latency)

    def report_failure(self, proxy):
        self.scorer.record(proxy, success=False, latency=100.0, blocked=True)
