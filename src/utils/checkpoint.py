"""
Checkpointing genérico para procesos largos y reanudables (scraping,
geocodificación). Guarda progreso en JSON, clave -> registro con estado.

Estados posibles: PENDING, SUCCESS, PARTIAL, BLOCKED, NOT_FOUND, ERROR.
"""

import json
from pathlib import Path
from typing import Any, Dict

CHECKPOINT_DIR = Path(__file__).resolve().parents[2] / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


class CheckpointStore:
    def __init__(self, filename: str):
        self.path = CHECKPOINT_DIR / filename
        self.data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = json.load(f)

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False, default=str)

    def get(self, key: str) -> Dict[str, Any] | None:
        return self.data.get(key)

    def is_done(self, key: str) -> bool:
        record = self.data.get(key)
        return bool(record) and record.get("status") in {"SUCCESS", "PARTIAL", "BLOCKED", "NOT_FOUND"}

    def set(self, key: str, record: Dict[str, Any], autosave: bool = True) -> None:
        self.data[key] = record
        if autosave:
            self.save()

    def pending_keys(self, all_keys: list[str]) -> list[str]:
        return [k for k in all_keys if not self.is_done(k)]

    def summary(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for record in self.data.values():
            status = record.get("status", "UNKNOWN")
            counts[status] = counts.get(status, 0) + 1
        return counts
