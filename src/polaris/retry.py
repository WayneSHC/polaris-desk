"""通用 retry primitive（R2 W2 D7 / SC-006）。

純函式、零 LLM / graph 耦合：給定一個 thunk ``fn``，對「可重試」例外做
exponential backoff 重試；分類交給 :func:`is_transient`（暫時性 vs 永久性）。

``sleep`` 經模組層 :func:`default_sleep` 間接呼叫，測試可注入 no-op / recorder
→ 不真的等待、確定可測（憲法成本紀律：CI token=0、不拖慢）。

兩個消費者（見 design 2026-06-03）：
- Tier 1：LLM 邊界（make_plan / make_draft）—— Gemini 暫時性錯誤重試後才降級 fallback。
- Tier 2：節點層保險絲（@traced）—— R4 接真實 I/O 後的節點暫時性失敗。
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")

#: 視為「暫時性、值得重試」的 HTTP 狀態碼（逾時 / 衝突 / 限流 / 5xx）。
_TRANSIENT_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

#: type 名稱（小寫）含這些片語視為暫時性（涵蓋 timeout / 連線 / 服務不可用等）。
_TRANSIENT_NAME_HINTS = (
    "timeout",
    "unavailable",
    "servererror",
    "deadline",
    "connection",
    "temporar",
)


def is_transient(exc: BaseException) -> bool:
    """例外是否為「暫時性、值得重試」。

    判斷依據（任一命中即 True）：
    - 帶 HTTP 狀態碼屬性（``code`` / ``status_code`` / ``status``）且 ∈ 可重試集合。
    - type 名稱含暫時性片語（timeout / connection / servererror …）。

    其餘一律 False —— 特別是 ``ValueError``（如 planner 的「empty query」）與
    永久性 4xx（400/401/403/404/422），絕不重試。
    """
    for attr in ("code", "status_code", "status"):
        val = getattr(exc, attr, None)
        if isinstance(val, bool):  # bool 是 int 子類，排除掉
            continue
        if isinstance(val, int) and val in _TRANSIENT_STATUS:
            return True
    name = type(exc).__name__.lower()
    return any(hint in name for hint in _TRANSIENT_NAME_HINTS)


def default_sleep(seconds: float) -> None:
    """退避等待的預設實作；獨立成函式讓測試可 monkeypatch 成 no-op。"""
    time.sleep(seconds)


def call_with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_on: Callable[[BaseException], bool] = is_transient,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """跑 ``fn()``；遇可重試例外則退避重試，用盡 / 不可重試則 re-raise。

    - ``attempts``：總嘗試次數（含第一次），需 ≥ 1。
    - backoff：第 k 次失敗（非最後一次）後等待 ``min(max_delay, base_delay*2**(k-1))``。
    - ``retry_on``：判斷例外是否可重試的 predicate，預設 :func:`is_transient`。
    - ``sleep``：等待實作；``None`` → 用模組層 :func:`default_sleep`（測試可改）。
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    _sleep = sleep if sleep is not None else default_sleep
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — 由 retry_on 決定是否吞下重試
            if i >= attempts or not retry_on(exc):
                raise
            _sleep(min(max_delay, base_delay * (2 ** (i - 1))))
    raise RuntimeError("unreachable")  # pragma: no cover — 迴圈必 return 或 raise


__all__ = ["is_transient", "default_sleep", "call_with_retry"]
