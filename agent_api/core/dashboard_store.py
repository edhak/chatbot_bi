"""
Persistencia del dashboard ejecutivo (sin autenticación por ahora).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_STORE_PATH = Path(os.getenv("DASHBOARD_STORE_PATH", str(_DATA_DIR / "dashboard.json")))
_LOCK = threading.Lock()


def _ensure_store_dir() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_store() -> dict[str, Any]:
    return {"version": 1, "items": []}


def _load_unlocked() -> dict[str, Any]:
    _ensure_store_dir()
    if not _STORE_PATH.exists():
        return _default_store()
    try:
        data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return _default_store()


def _save_unlocked(data: dict[str, Any]) -> None:
    _ensure_store_dir()
    _STORE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_items() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_load_unlocked().get("items", []))


def find_by_id(item_id: str) -> dict[str, Any] | None:
    with _LOCK:
        for item in _load_unlocked().get("items", []):
            if item.get("id") == item_id:
                return dict(item)
    return None


def find_by_dax(dax_query: str) -> dict[str, Any] | None:
    normalized = dax_query.strip()
    with _LOCK:
        for item in _load_unlocked().get("items", []):
            if str(item.get("dax_query", "")).strip() == normalized:
                return dict(item)
    return None


def add_item(*, title: str, question: str, dax_query: str) -> dict[str, Any]:
    now = _now_iso()
    item = {
        "id": str(uuid.uuid4()),
        "title": title.strip() or "Indicador BI",
        "question": question.strip(),
        "dax_query": dax_query.strip(),
        "created_at": now,
        "updated_at": now,
        "last_refresh_at": None,
        "last_error": None,
    }
    with _LOCK:
        data = _load_unlocked()
        items = data.setdefault("items", [])
        for existing in items:
            if str(existing.get("dax_query", "")).strip() == item["dax_query"]:
                return dict(existing)
        items.append(item)
        _save_unlocked(data)
    return item


def remove_item(item_id: str) -> bool:
    with _LOCK:
        data = _load_unlocked()
        items = data.get("items", [])
        new_items = [item for item in items if item.get("id") != item_id]
        if len(new_items) == len(items):
            return False
        data["items"] = new_items
        _save_unlocked(data)
    return True


def update_item_meta(
    item_id: str,
    *,
    last_refresh_at: str | None = None,
    last_error: str | None = None,
) -> dict[str, Any] | None:
    with _LOCK:
        data = _load_unlocked()
        for item in data.get("items", []):
            if item.get("id") == item_id:
                if last_refresh_at is not None:
                    item["last_refresh_at"] = last_refresh_at
                if last_error is not None:
                    item["last_error"] = last_error
                item["updated_at"] = _now_iso()
                _save_unlocked(data)
                return dict(item)
    return None
