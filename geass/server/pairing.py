"""扫码配对：短期一次性配对码换取访问 Token。

二维码只包含配对码（``/#pair=<code>``），配对码在服务端内存中生成、
默认 300 秒过期且只能使用一次；兑换成功后由 API 返回真正的访问 Token，
避免 Token 出现在 URL、二维码或访问日志中。
"""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from dataclasses import dataclass

DEFAULT_TTL = 300.0
MIN_TTL = 30.0
MAX_TTL = 3600.0
RATE_LIMIT_ATTEMPTS = 10
RATE_LIMIT_WINDOW = 60.0


class PairingError(RuntimeError):
    """配对码无效、过期、已使用或尝试过于频繁。"""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class PairingCode:
    code: str
    expires_at: float
    used: bool = False


def normalize_ttl(value: float) -> float:
    return max(MIN_TTL, min(MAX_TTL, float(value)))


class PairingManager:
    """内存中的配对码表；服务重启即全部失效。"""

    def __init__(self, ttl: float = DEFAULT_TTL) -> None:
        self.ttl = normalize_ttl(ttl)
        self._codes: dict[str, PairingCode] = {}
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def create(self) -> PairingCode:
        now = time.time()
        code = secrets.token_urlsafe(32)
        entry = PairingCode(code=code, expires_at=now + self.ttl)
        with self._lock:
            self._prune_locked(now)
            self._codes[code] = entry
        return entry

    def redeem(self, code: str, token: str, *, client: str = "") -> str:
        """校验并消费配对码，返回真实 Token。"""
        now = time.time()
        candidate = str(code or "")
        with self._lock:
            self._check_rate_locked(client, now)
            entry = None
            for stored in self._codes.values():
                if hmac.compare_digest(stored.code, candidate):
                    entry = stored
                    break
            if entry is None:
                self._record_failure_locked(client, now)
                raise PairingError("invalid", "配对码无效")
            if entry.used:
                self._record_failure_locked(client, now)
                raise PairingError("used", "配对码已被使用")
            if entry.expires_at <= now:
                self._codes.pop(entry.code, None)
                self._record_failure_locked(client, now)
                raise PairingError("expired", "配对码已过期")
            entry.used = True
            return token

    def pending_count(self) -> int:
        now = time.time()
        with self._lock:
            self._prune_locked(now)
            return sum(1 for entry in self._codes.values() if not entry.used)

    # ---------- 内部 ----------

    def _prune_locked(self, now: float) -> None:
        for code, entry in list(self._codes.items()):
            if entry.expires_at <= now:
                self._codes.pop(code, None)

    def _check_rate_locked(self, client: str, now: float) -> None:
        key = str(client or "")
        if not key:
            return
        failures = [
            stamp for stamp in self._failures.get(key, []) if now - stamp <= RATE_LIMIT_WINDOW
        ]
        self._failures[key] = failures
        if len(failures) >= RATE_LIMIT_ATTEMPTS:
            raise PairingError("rate_limited", "尝试过于频繁，请稍后再试")

    def _record_failure_locked(self, client: str, now: float) -> None:
        key = str(client or "")
        if not key:
            return
        self._failures.setdefault(key, []).append(now)
