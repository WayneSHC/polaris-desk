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


NodeFn = Callable[[dict[str, Any]], dict[str, Any] | None]


def traced(node_name: str) -> Callable[[NodeFn], NodeFn]:
    """工廠：回一個包住節點函式的裝飾器。

    包裝後的函式契約：

    - 接收 LangGraph state（dict）。
    - 回 state patch（dict）；保證含 ``trace`` key（list of 1 個 NodeTrace）。
    - 例外時 patch 額外含 ``halt: True``，且**不**含原節點想 set 的欄位。
    - 不會修改傳入的 state dict。
    """

    if not node_name or not node_name.strip():
        raise ValueError("traced(node_name) requires a non-empty node_name")

    def decorator(fn: NodeFn) -> NodeFn:
        @functools.wraps(fn)
        def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            input_keys = sorted(state.keys())
            start = time.perf_counter()

            try:
                patch = fn(state) or {}
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

        return wrapper

    return decorator


__all__ = ["traced"]
