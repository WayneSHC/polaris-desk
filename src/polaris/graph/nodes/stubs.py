"""5 個 LangGraph 節點的確定性 stub 實作（W1 D1 US1）。

每節點：
- 用 :func:`polaris.graph.nodes.trace.traced` 裝飾，自動 emit NodeTrace。
- **無 LLM / 無網路 / 無亂數** — token cost = 0，3 次重跑結果相同（SC-006）。
- 後續週次 R3/R4/R6 把真實作推進來時，只在這個檔案逐顆替換；workflow.py
  的 wiring 不變（FR-007 / SC-005）。
"""
from __future__ import annotations

from typing import Any

from polaris.graph.nodes.trace import traced
from polaris.graph.state import Citation


# ---------------------------------------------------------------------------
# 固定 fake 資料（不在函式內構造，確保多次呼叫回 byte-identical 物件）
# ---------------------------------------------------------------------------

_STUB_CITATION = Citation(
    source_id="stub-tsmc-2025Q1-001",
    snippet="（v0 stub）法說頁碼 X：營收 YYY 億元，YoY 約 12.34%。",
    origin="stub",
)

_STUB_DRAFT = (
    "（v0 假答案）依據引用來源，2025 Q1 營收 YoY 約 12.34%。"
    "本系統目前以 stub 假資料展示工作流骨架。"
)


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

@traced("planner")
def planner(state: dict[str, Any]) -> dict[str, Any]:
    """FR-008：空字串 / 全空白 query → raise，讓 @traced 設 halt=True。

    其餘情況回固定 3 步驟計畫。
    """
    query = (state.get("query") or "").strip()
    if not query:
        raise ValueError("empty query")
    return {"plan": ["擷取相關段落", "計算指標", "撰寫並標引用"]}


@traced("retriever")
def retriever(state: dict[str, Any]) -> dict[str, Any]:
    """W1 D1：固定回 1 條 stub context。"""
    return {
        "contexts": [
            {
                "source_id": _STUB_CITATION.source_id,
                "text": _STUB_CITATION.snippet,
            }
        ]
    }


@traced("calculator")
def calculator(state: dict[str, Any]) -> dict[str, Any]:
    """W1 D1：固定回一組 fake 計算結果。"""
    return {"calculations": {"YoY_pct": 12.34}}


@traced("writer")
def writer(state: dict[str, Any]) -> dict[str, Any]:
    """W1 D1：合規假草稿 + 1 條 stub citation。

    US2 會新增 ``--stub-buysell`` 路徑讓本節點改回含買賣建議的草稿，
    驗證 compliance 攔截行為；現階段（US1）只回合規版本。
    """
    return {
        "draft": _STUB_DRAFT,
        "citations": [_STUB_CITATION],
    }


@traced("compliance")
def compliance(state: dict[str, Any]) -> dict[str, Any]:
    """W1 D1 US1：passthrough — 把 draft 原封不動當 answer，標記 passed。

    US2 會引入 ``polaris.graph.compliance.apply_compliance`` 做 6 關鍵字攔截。
    """
    return {
        "answer": state.get("draft", ""),
        "compliance_status": "passed",
    }


__all__ = ["planner", "retriever", "calculator", "writer", "compliance"]
