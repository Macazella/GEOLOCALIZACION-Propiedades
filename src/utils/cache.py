"""
Cache en disco para evitar repetir requests de scraping o consultas de
geocodificación sobre la misma URL / dirección normalizada (punto 7 del
ajuste al plan). Un archivo JSON por clave, en data/cache/<namespace>/.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

CACHE_ROOT = Path(__file__).resolve().parents[2] / "data" / "cache"


def _key_to_filename(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"{digest}.json"


class DiskCache:
    def __init__(self, namespace: str):
        self.dir = CACHE_ROOT / namespace
        self.dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Optional[Any]:
        path = self.dir / _key_to_filename(key)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get("value")

    def set(self, key: str, value: Any) -> None:
        path = self.dir / _key_to_filename(key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"key": key, "value": value}, f, indent=2, ensure_ascii=False, default=str)

    def has(self, key: str) -> bool:
        return (self.dir / _key_to_filename(key)).exists()
