"""
Traza de depuración del agente BI (pasos, tiempos, mensajes).
"""

from __future__ import annotations

import os
import time
from typing import Any


class AgentDebugTrace:
    def __init__(self) -> None:
        self._start = time.perf_counter()
        self.entries: list[dict[str, Any]] = []

    def log(self, step: str, message: str, level: str = "info") -> None:
        entry = {
            "step": step,
            "message": message,
            "level": level,
            "elapsed_ms": int((time.perf_counter() - self._start) * 1000),
        }
        self.entries.append(entry)
        if os.getenv("AGENT_DEBUG", "true").lower() == "true":
            print(f"[AGENT {entry['elapsed_ms']:>5}ms] [{level.upper()}] {step}: {message}")

    def to_list(self) -> list[dict[str, Any]]:
        return list(self.entries)


def is_debug_enabled() -> bool:
    return os.getenv("AGENT_DEBUG", "true").lower() == "true"
