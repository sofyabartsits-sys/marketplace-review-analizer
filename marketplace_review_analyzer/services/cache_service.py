from __future__ import annotations

import hashlib
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

CACHE_PATH = Path("outputs/cache.json")


class CacheService:
    def __init__(self, path: Path = CACHE_PATH, ttl_seconds: int = 6 * 60 * 60) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("{}", encoding="utf-8")

    def make_key(self, marketplace: str, article: str | None, date_from: date | None, date_to: date | None, data_type: str) -> str:
        raw = "|".join([marketplace, article or "", str(date_from or ""), str(date_to or ""), data_type])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Any | None:
        data = self._read()
        entry = data.get(key)
        if not entry:
            return None
        if time.time() - entry.get("created_at", 0) > self.ttl_seconds:
            data.pop(key, None)
            self._write(data)
            return None
        return entry.get("value")

    def set(self, key: str, value: Any) -> None:
        data = self._read()
        data[key] = {"created_at": time.time(), "value": value}
        self._write(data)

    def clear(self) -> None:
        self._write({})

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
