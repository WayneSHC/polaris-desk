"""5 個 LangGraph 節點的確定性 stub 實作（W1 D1 US1）。

每節點：
- 用 :func:`polaris.graph.nodes.trace.traced` 裝飾，自動 emit NodeTrace。
- **無 LLM / 無網路 / 無亂數** — token cost = 0，3 次重跑結果相同（SC-006）。
- 後續週次 R3/R4/R6 把真實作推進來時，只在這個檔案逐顆替換；workflow.py
  的 wiring 不變（FR-007 / SC-005）。
"""
from __future__ import annotations

from typing import Any

from polaris.graph.compliance import apply_compliance
from polaris.graph.nodes import planner_agent, writer_agent
from polaris.graph.nodes.trace import traced
from polaris.graph.state import Citation
from polaris.llm.gemini import active_llm


# ---------------------------------------------------------------------------
# 固定 fake 資料（不在函式內構造，確保多次呼叫回 byte-identical 物件）
# ---------------------------------------------------------------------------

_STUB_CITATION = Citation(
    source_id="stub-tsmc-2025Q1-001",
    snippet="（v0 stub）法說頁碼 X：營收 YYY 億元，YoY 約 12.34%。",
    origin="stub",
)

#: US2 demo 用：含買賣建議的 stub 草稿，CLI `--stub-buysell` 與測試會用 monkeypatch
#: 把 :func:`writer` 換成 :func:`writer_with_buysell`，驗證 Compliance 攔截行為。
_BUYSELL_DRAFT = (
    "（demo）依據法說會分析師說法，現在建議買進台積電。"
    "本句僅供 W1 US2 攔截示範，正常 stub 路徑不會回此文字。"
)


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

@traced("planner")
def planner(state: dict[str, Any]) -> dict[str, Any]:
    """Planner Agent v0（R2 W1 D2）。

    - FR-008：空字串 / 全空白 query → raise，讓 @traced 設 halt=True。
    - 否則用 :func:`planner_agent.make_plan` 拆步驟（有金鑰走 Gemini Flash、
      否則確定性 fallback）。``active_llm`` 在此模組命名空間，測試可 monkeypatch。
    """
    query = (state.get("query") or "").strip()
    if not query:
        raise ValueError("empty query")
    return {"plan": planner_agent.make_plan(query, active_llm())}


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
    """Calculator v0（R2 W1 D3）— 維持確定性假值。

    真實財務指標計算需 R4 的結構化資料（BigQuery / 財報表）尚未進來，
    故 v0 先回固定值；待 R4 資料就緒後在此節點接真實計算（介面不變）。
    """
    return {"calculations": {"YoY_pct": 12.34}}


@traced("writer")
def writer(state: dict[str, Any]) -> dict[str, Any]:
    """Writer Agent v0（R2 W1 D3）。

    依 ``contexts`` 產生帶引用草稿（有金鑰走 Gemini Pro、否則確定性 fallback），
    citations 由 contexts 接地而來。草稿仍交由下游 Compliance 節點守 NFR-031。
    """
    query = state.get("query", "")
    contexts = state.get("contexts", [])
    draft, citations = writer_agent.make_draft(query, contexts, active_llm())
    return {"draft": draft, "citations": citations}


@traced("writer")
def writer_with_buysell(state: dict[str, Any]) -> dict[str, Any]:
    """US2 demo：故意回含「建議買進」的草稿，驗證 Compliance 攔截。

    CLI ``--stub-buysell`` 旗標會用 :func:`build_workflow_with_buysell_writer`
    或 monkeypatch 把 :func:`writer` 換成本函式。**正常路徑不會用到。**
    """
    return {
        "draft": _BUYSELL_DRAFT,
        "citations": [_STUB_CITATION],
    }


@traced("compliance")
def compliance(state: dict[str, Any]) -> dict[str, Any]:
    """US2：呼叫 :func:`polaris.graph.compliance.apply_compliance` 做 6 關鍵字攔截。

    - 合規 → ``answer = draft``、``compliance_status = "passed"``
    - 命中關鍵字 → ``answer = SAFE_MESSAGE``、``compliance_status = "blocked"``
    """
    draft = state.get("draft", "")
    final, status = apply_compliance(draft)
    return {
        "answer": final,
        "compliance_status": status,
    }


__all__ = [
    "planner",
    "retriever",
    "calculator",
    "writer",
    "writer_with_buysell",
    "compliance",
]
