import json
from pathlib import Path

SCORE_FILE = Path("data/proxy_scores.json")

class ProxyScore:
    def __init__(self):
        SCORE_FILE.parent.mkdir(exist_ok=True)
        if SCORE_FILE.exists():
            self.data = json.loads(SCORE_FILE.read_text())
        else:
            self.data = {}

    def record(self, proxy, success, latency, blocked=False):
        p = self.data.setdefault(proxy, {
            "success": 0,
            "fail": 0,
            "blocked": 0,
            "latencies": []
        })

        if success:
            p["success"] += 1
            p["latencies"].append(latency)
        else:
            p["fail"] += 1

        if blocked:
            p["blocked"] += 1

        self.save()

    def score(self, proxy):
        p = self.data.get(proxy)
        if not p:
            return 50
        avg_latency = sum(p["latencies"]) / len(p["latencies"]) if p["latencies"] else 5
        return max(1, 100 - avg_latency * 10 - p["blocked"] * 20 - p["fail"] * 5)

    def save(self):
        SCORE_FILE.write_text(json.dumps(self.data, indent=2))