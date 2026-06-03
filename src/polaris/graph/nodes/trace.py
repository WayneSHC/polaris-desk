"""@traced 節點裝飾器 — 自動 emit NodeTrace、安全捕捉節點例外。

對應 spec 001-langgraph-skeleton：

- **FR-006**：每個節點要有 trace（node_name / status / input_keys / output_keys / elapsed_ms）。
- **FR-009**：節點例外時不得讓下游吃到 undefined 狀態 → 裝飾器吞掉例外、設 ``halt=True``。
- **FR-007 / SC-005**：裝飾器集中處理，個別節點函式不需重複樣板，方便換真實作。

設計選擇（research.md §2 / §3）：

- 裝飾器只回「單筆 trace」的 patch；多次累加由 LangGraph reducer
  ``Annotated[list[NodeTrace], operator.add]`` 在 state 層處理。
- 例外路徑回 ``{"trace": [error_trace], "halt": True}``，**不**回節點原本想 set
  的部分 patch（避免半成品狀態）。
"""
from __future__ import annotations

import functools
import time
from typing import Any, Callable

from polaris.graph.state import NodeTrace
from polaris.retry import call_with_retry, is_transient


NodeFn = Callable[[dict[str, Any]], dict[str, Any] | None]


def traced(
    node_name: str,
    *,
    retries: int = 0,
    retry_on: Callable[[BaseException], bool] = is_transient,
) -> Callable[[NodeFn], NodeFn]:
    """工廠：回一個包住節點函式的裝飾器。

    包裝後的函式契約：

    - 接收 LangGraph state（dict）。
    - 回 state patch（dict）；保證含 ``trace`` key（list of 1 個 NodeTrace）。
    - 例外時 patch 額外含 ``halt: True``，且**不**含原節點想 set 的欄位。
    - 不會修改傳入的 state dict。

    D7 節點層保險絲（opt-in）：

    - ``retries>0`` 時，節點呼叫包進 :func:`polaris.retry.call_with_retry`
      （共 ``retries+1`` 次嘗試），重試發生在下方 try/except **內**——用盡後
      例外照樣變 error trace + ``halt=True``（FR-009 不變），且整個節點只
      emit **一筆** trace（不因重試而暴增）。
    - ``retry_on`` 預設 :func:`is_transient`：永久性錯誤（如 ``ValueError``
      「empty query」）不重試。
    - ``retries=0``（預設）→ 與既有行為完全一致（單次嘗試）。
    """

    if not node_name or not node_name.strip():
        raise ValueError("traced(node_name) requires a non-empty node_name")

    def decorator(fn: NodeFn) -> NodeFn:
        @functools.wraps(fn)
        def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            input_keys = sorted(state.keys())
            start = time.perf_counter()

            def _attempt() -> dict[str, Any]:
                return fn(state) or {}

            try:
                patch = (
                    call_with_retry(_attempt, attempts=retries + 1, retry_on=retry_on)
                    if retries > 0
                    else _attempt()
                )
                elapsed_ms = max(0, int((time.perf_counter() - start) * 1000))
                trace = NodeTrace(
                    node_name=node_name,
                    status="ok",
                    input_keys=input_keys,
                    output_keys=sorted(patch.keys()),
                    elapsed_ms=elapsed_ms,
                )
                return {**patch, "trace": [trace]}

            except Exception as exc:  # noqa: BLE001 — 故意吞，FR-009
                elapsed_ms = max(0, int((time.perf_counter() - start) * 1000))
                trace = NodeTrace(
                    node_name=node_name,
                    status="error",
                    input_keys=input_keys,
                    output_keys=[],
                    error_message=f"{type(exc).__name__}: {exc}",
                    elapsed_ms=elapsed_ms,
                )
                return {"trace": [trace], "halt": True}

        # 重試政策 metadata：方便診斷 / 測試查「哪些節點接了保險絲」。
        wrapper._traced_node = node_name
        wrapper._traced_retries = retries
        return wrapper

    return decorator


__all__ = ["traced"]
