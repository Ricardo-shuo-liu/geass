"""进化系统包：空闲进化引擎 + POT 反思系统。"""

from __future__ import annotations

from .engine import (
    CONTEXT_HISTORY_LIMIT,
    CONTEXT_MEMORY_LIMIT,
    EVOLUTION_SYSTEM_PROMPT,
    HISTORY_LIMIT,
    NAME_RE,
    POLL_INTERVAL,
    ActivityCallback,
    EvolutionEngine,
    StatusCallback,
)
from .pot import ROT, POTStore, default_pot_path

__all__ = [
    "ActivityCallback",
    "CONTEXT_HISTORY_LIMIT",
    "CONTEXT_MEMORY_LIMIT",
    "EVOLUTION_SYSTEM_PROMPT",
    "EvolutionEngine",
    "HISTORY_LIMIT",
    "NAME_RE",
    "POLL_INTERVAL",
    "POTStore",
    "ROT",
    "StatusCallback",
    "default_pot_path",
]
