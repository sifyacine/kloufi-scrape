import json
from pathlib import Path
from threading import Lock

class JSONStorage:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = Lock()
        self.path.parent.mkdir(exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}")

    def read(self):
        with self.lock:
            return json.loads(self.path.read_text())

    def write(self, data):
        with self.lock:
            self.path.write_text(json.dumps(data, indent=2))