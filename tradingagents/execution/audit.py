"""Append-only JSONL audit log for every order attempt."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_audit_path() -> Path:
    home = Path(os.path.expanduser("~")) / ".tradingagents" / "logs"
    home.mkdir(parents=True, exist_ok=True)
    return home / "orders.jsonl"


class OrderAuditLog:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_audit_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict[str, Any]) -> None:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
