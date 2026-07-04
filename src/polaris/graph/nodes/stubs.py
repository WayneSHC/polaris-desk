"""5 個 LangGraph 節點的確定性 stub 實作（W1 D1 US1）。

每節點：
- 用 :func:`polaris.graph.nodes.trace.traced` 裝飾，自動 emit NodeTrace。
- **無 LLM / 無網路 / 無亂數** — token cost = 0，3 次重跑結果相同（SC-006）。
- 後續週次 R3/R4/R6 把真實作推進來時，只在這個檔案逐顆替換；workflow.py
  的 wiring 不變（FR-007 / SC-005）。
"""
from __future__ import annotations

from typing import Any

from polaris.graph import temporal
from polaris.graph.nodes import compliance_agent, planner_agent, writer_agent
from polaris.graph.nodes.trace import traced
from polaris.graph.redaction import redact
from polaris.graph.state import Citation
from polaris.llm.gemini import active_llm
from polaris.ontology import company_label, company_name, detect_tickers
from polaris.retrieval.retriever import PUBLIC_VIEWER, active_retriever


# ---------------------------------------------------------------------------
# 固定 fake 資料（不在函式內構造，確保多次呼叫回 byte-identical 物件）
# ---------------------------------------------------------------------------

_STUB_CITATION = Citation(
    source_id="stub-tsmc-2025Q1-001",
    snippet="（v0 stub）法說頁碼 X：營收 YYY 億元，YoY 約 12.34%。",
    origin="stub",
)

#: W2 D6 用的迷你假語料：每季一筆，retriever 依 Temporal Anchoring 解析的
#: 季別過濾。R4 接真實向量檢索後，這個 dict 換成 VectorStore.search(filters=...)，
#: retriever 的「依 period 取資料」契約不變。
_STUB_CORPUS: dict[str, dict[str, str]] = {
    q: {
        "source_id": f"stub-2330-{q}",
        "text": f"（v0 stub）台積電 {q} 法說摘要：營收與毛利率資料。",
        "period": q,
    }
    for q in ("2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1")
}

#: 問題未含期間語句時的預設季別（取最新一季）。
_DEFAULT_QUARTER = "2025Q1"

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
    return {
        "plan": planner_agent.make_plan(query, active_llm()),
        # W2 D6 Temporal Anchoring；anchor 走 DB 最新已公布季（修「最近一季」凍結於
        # 2025Q1 的根因），無憑證時 active_anchor 退回 DEFAULT_ANCHOR、CI 確定性不變。
        "period": temporal.parse_period(query, anchor=temporal.active_anchor()),
    }


#: retriever-internal origin → Citation literal（vector 通道對應 "embedding"）。
_CITATION_ORIGINS = {"stub", "bm25", "embedding", "colpali", "rerank", "news"}


def _citation_origin(raw: str | None) -> str:
    if raw == "vector":
        return "embedding"
    return raw if raw in _CITATION_ORIGINS else "bm25"


#: 查法說會意圖 → 只取法說會證據（doc_type 過濾），避免抓到新聞 / 重大訊息（修 R6 #2）。
_EARNINGS_CALL_HINTS = ("法說", "法人說明會", "earnings call", "逐字稿", "conference call")

#: 法說會證據的 canonical doc_type 有兩種：逐字稿（transcript）與簡報（presentation，
#: ingest_ticker.py 入庫用的值）。兩種都要查——某季只有簡報入庫時，只查 transcript
#: 會誤回「資料不足」（同 PR #34 在 /research 修過的缺漏，這裡是 /ask 路徑）。
_EARNINGS_CALL_DOC_TYPES: tuple[str, ...] = ("transcript", "presentation")


def _wants_earnings_call(query: str) -> bool:
    q = (query or "").lower()
    return any(hint.lower() in q for hint in _EARNINGS_CALL_HINTS)


def _real_contexts(
    retriever_obj: Any, query: str, quarters: list[str] | None, viewer: str
) -> list[dict[str, Any]]:
    """HybridRetriever SearchResults → writer 形狀的 context dict（依 id 去重）。

    依查詢偵測到的公司 ticker × anchored 季別逐一查詢：
    - **公司過濾（修 R6 #1）**：問單一公司只取該公司；比較題涵蓋多家、citation 落在
      正確公司；未偵測到公司 → 不加公司過濾（維持原行為）。
    - **doc_type 過濾（修 R6 #2）**：問法說會時限定法說會 doc_type（transcript +
      presentation 各查一次、依 id 去重合併），不抓新聞 / 重大訊息。
    - viewer 透傳做 owner-scoped 過濾（issue #32）。
    """
    contexts: list[dict[str, Any]] = []
    seen: set[str] = set()
    tickers = detect_tickers(query) or [None]
    doc_types: tuple[str | None, ...] = (
        _EARNINGS_CALL_DOC_TYPES if _wants_earnings_call(query) else (None,)
    )
    for ticker in tickers:
        for q in quarters or [None]:
            for doc_type in doc_types:
                filters: dict[str, Any] = {"viewer": viewer}
                if ticker:
                    filters["company"] = ticker
                if q:
                    filters["period"] = q
                if doc_type:
                    filters["doc_type"] = doc_type
                for r in retriever_obj.retrieve(query, filters=filters):
                    if r.id in seen:
                        continue
                    seen.add(r.id)
                    meta = r.metadata or {}
                    contexts.append(
                        {
                            "source_id": r.id,
                            "text": r.content,
                            "period": r.period,
                            "company": r.company,  # ticker
                            "company_name": company_name(r.company),  # canonical 中文名 / None
                            "origin": _citation_origin(meta.get("origin")),
                            # v_chunk_semantic 欄位透傳到 /ask citation（缺值 → None，不編造）。
                            "event_key": meta.get("event_key"),
                            "source_key": meta.get("source_key"),
                            "published_yyyymm": meta.get("published_yyyymm"),
                            "doc_type": meta.get("doc_type"),
                            "fiscal_period": meta.get("fiscal_period") or r.period,
                            "page_num": meta.get("page_num"),
                            "source_file": meta.get("source_file"),
                        }
                    )
    return contexts


def _maybe_pivot_unreported_quarter(
    period: Any, quarters: list[str] | None
) -> tuple[list[str] | None, str]:
    """未公布季退回：顯式問「最新已公布季的下一季」（剛結束、財報未出的當季，如已公布到
    2026Q1 時問 2026Q2）時，補上最新已公布季一起檢索，並回 note 讓 writer 誠實說明。

    只退回「下一季」這一種——更遠的未來季（如 2030Q1）維持誠實「資料不足」、不硬退回到
    無關的舊季。回 ``(quarters, note)``；不觸發時 note 為空字串、quarters 原樣。
    """
    if not (period and getattr(period, "kind", None) == "quarter" and quarters):
        return quarters, ""
    anchor = temporal.active_anchor()
    if temporal.next_quarter(anchor) not in quarters:
        return quarters, ""
    next_q = temporal.next_quarter(anchor)
    augmented = quarters + ([anchor] if anchor not in quarters else [])
    note = (
        f"使用者詢問的 {next_q} 財報尚未公布（最新已公布季為 {anchor}）。"
        f"請在回答開頭明確說明 {next_q} 尚未公布，再以 {anchor} 等已公布資料回覆。"
    )
    return augmented, note


@traced("retriever", retries=2)
def retriever(state: dict[str, Any]) -> dict[str, Any]:
    """依 Temporal Anchoring 解析的季別取語料。

    - **真路徑（有金鑰）**：:func:`active_retriever` 回 HybridRetriever（BM25 +
      vector + Cohere Rerank），對 ``polaris_core`` 查真 chunks；每季一次、依 viewer
      做 owner-scoped 過濾（issue #32）；無季別 → 一次無過濾語意查詢。
    - **stub 路徑（CI / 無金鑰）**：``active_retriever`` 回 None，沿用 W2 D6 迷你假
      語料依季別過濾（未入庫季別 → 0 條，下游誠實回「資料不足」），token-free。

    D7 保險絲（retries=2）：真路徑 DB / 網路暫時性失敗自動重試；stub 走記憶體 dict
    不會失敗，對既有行為零影響。
    """
    period = state.get("period")
    quarters = list(period.quarters) if period and period.quarters else None
    viewer = state.get("viewer", PUBLIC_VIEWER)

    quarters, note = _maybe_pivot_unreported_quarter(period, quarters)

    real = active_retriever()
    if real is None:
        stub_quarters = quarters or [_DEFAULT_QUARTER]
        contexts = [_STUB_CORPUS[q] for q in stub_quarters if q in _STUB_CORPUS]
        return {"contexts": contexts, "period_note": note}

    contexts = _real_contexts(real, state.get("query", ""), quarters, viewer)
    return {"contexts": contexts, "period_note": note}


def _metric_context(ticker: str, quarter: str, row: dict[str, Any], *, extra: str = "") -> dict[str, Any]:
    """BQ financial_metrics 列 → writer 形狀的 context dict（數字可被引用）。

    origin 用 "bm25"（結構化指標本就進 BM25 語料，見 bigquery_store 的
    financial corpus 合成），source_id 沿用 BQ 列的 source_id → 前端引用
    面板行為與既有指標引用一致。
    """
    label = row.get("metric_name") or row.get("metric_id") or ""
    unit = row.get("unit") or ""
    value = row.get("value")
    text = f"{company_label(ticker)} {quarter} {label} {value:,g} {unit}（BQ financial_metrics）"
    if extra:
        text += f"；{extra}"
    return {
        "source_id": str(row.get("source_id") or f"fm-{ticker}-{quarter}-{row.get('metric_id')}"),
        "text": text,
        "period": quarter,
        "company": ticker,
        "company_name": company_name(ticker),
        "origin": "bm25",
        "doc_type": None,
        "fiscal_period": quarter,
    }


#: calculator 真路徑抓的 metric_id（gross_margin 非入庫指標，由 gross_profit / revenue 推導）。
#: eps / net_income 一併餵進 contexts——presentation chunk 常把 EPS 切成獨立子塊而檢索
#: 不到（E013 日月光根因），這條結構化後路確保數字題有可引用的接地來源。
_CALC_METRIC_IDS = ("revenue", "revenue_yoy", "gross_profit", "eps", "net_income")

#: 直接入 contexts 的原生指標（有值就餵，不做推導）；revenue 已由專屬分支處理。
_PASSTHROUGH_METRIC_IDS = ("eps", "net_income")


def _structured_calculations(
    query: str, quarters: list[str] | None, *, store: Any | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """從 BQ financial_metrics 算真實指標；不可用（無憑證 / 無公司 / 無季別）回 None。

    - 抓 revenue / revenue_yoy / gross_profit；**毛利率非入庫 metric_id**（canonical
      14 種裡只有 gross_profit），由 ``gross_profit / revenue × 100`` 推導——這是
      eval Q001「找不到 2025Q1 毛利率」的根本解（法說 chunk 有沒有數字都算得出）。
    - 每個數字都帶 BQ 列的 source_id 進 contexts（引用接地：數字必有來源）；
      推導值標明公式與兩個來源列，不憑空編數字。
    """
    if store is None:
        from polaris.llm.gemini import available

        if not available():
            return None
        from polaris.config import settings
        from polaris.structured_store import StructuredStore

        store = StructuredStore(settings)

    tickers = detect_tickers(query)
    if not tickers or not quarters:
        return None

    calcs: dict[str, Any] = {}
    extra_contexts: list[dict[str, Any]] = []
    for ticker in tickers:
        for quarter in quarters:
            rows = {
                r["metric_id"]: r
                for r in store.list_financials(ticker=ticker, period=quarter, granularity="quarter")
                if r.get("metric_id") in _CALC_METRIC_IDS and r.get("value") is not None
            }
            rev, gp, yoy = rows.get("revenue"), rows.get("gross_profit"), rows.get("revenue_yoy")
            entry: dict[str, Any] = {}
            if rev:
                entry["revenue"] = {
                    "value": rev["value"], "unit": rev.get("unit"), "source_id": rev.get("source_id"),
                }
                extra_contexts.append(_metric_context(ticker, quarter, rev))
            if yoy:
                entry["revenue_yoy"] = {
                    "value": yoy["value"], "unit": yoy.get("unit"), "source_id": yoy.get("source_id"),
                }
                extra_contexts.append(_metric_context(ticker, quarter, yoy))
            if rev and gp and rev["value"] and (rev.get("unit") or "") == (gp.get("unit") or ""):
                margin = round(gp["value"] / rev["value"] * 100, 2)
                entry["gross_margin_pct"] = {
                    "value": margin,
                    "formula": "gross_profit / revenue × 100",
                    "derived_from": [gp.get("source_id"), rev.get("source_id")],
                }
                extra_contexts.append(
                    _metric_context(
                        ticker, quarter, gp,
                        extra=f"以同季營收推導毛利率 = {margin}%（gross_profit / revenue × 100）",
                    )
                )
            # eps / net_income 原生指標：有值就直接餵進 contexts（數字必有來源）。
            for mid in _PASSTHROUGH_METRIC_IDS:
                row = rows.get(mid)
                if row and row.get("value") is not None:
                    entry[mid] = {
                        "value": row["value"], "unit": row.get("unit"),
                        "source_id": row.get("source_id"),
                    }
                    extra_contexts.append(_metric_context(ticker, quarter, row))
            if entry:
                calcs[f"{ticker}:{quarter}"] = entry
    if not calcs:
        return None
    return calcs, extra_contexts


@traced("calculator", retries=2)
def calculator(state: dict[str, Any]) -> dict[str, Any]:
    """Calculator — 真路徑接 BQ financial_metrics，算 revenue / YoY / 推導毛利率。

    - **真路徑（有憑證）**：依查詢偵測的公司 × Temporal Anchoring 季別查
      `v_financial_metrics_semantic`，推導毛利率（非入庫指標）；算出的每個數字
      連同 BQ source_id 補進 contexts，讓 writer 草稿的數字可引用、可溯源。
    - **stub 路徑（CI / 無金鑰 / 查無資料）**：維持確定性假值（行為與 v0 相同，
      e2e determinism 測試不受影響）。

    D7 保險絲（retries=2）：BQ 暫時性失敗自動重試；重試耗盡的例外被吞成 stub
    fallback——結構化計算失敗不應 halt 整條 workflow（草稿仍可從 chunks 接地）。
    """
    period = state.get("period")
    quarters = list(period.quarters) if period and getattr(period, "quarters", None) else None
    try:
        result = _structured_calculations(state.get("query", ""), quarters)
    except Exception:  # noqa: BLE001 — 計算失敗退 stub，不中斷 workflow
        result = None
    if result is None:
        return {"calculations": {"YoY_pct": 12.34}}
    calcs, extra_contexts = result
    return {
        "calculations": calcs,
        # contexts 無 reducer（plain overwrite），需自行合併 retriever 的結果。
        "contexts": [*state.get("contexts", []), *extra_contexts],
    }


@traced("writer")
def writer(state: dict[str, Any]) -> dict[str, Any]:
    """Writer Agent v0（R2 W1 D3）。

    依 ``contexts`` 產生帶引用草稿（有金鑰走 Gemini Pro、否則確定性 fallback），
    citations 由 contexts 接地而來。草稿仍交由下游 Compliance 節點守 NFR-031。
    """
    query = state.get("query", "")
    contexts = state.get("contexts", [])
    # 未公布季退回提醒（retriever 設）：帶進草稿，讓答案誠實告知該季尚未公布。
    note = state.get("period_note", "")
    draft, citations = writer_agent.make_draft(query, contexts, active_llm(), note=note)
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
    """W2 D9：Compliance Agent — 6 關鍵字確定性 floor + Gemini smart 層。

    委派 :func:`compliance_agent.review`：floor 命中即攔（LLM 永不解除）；有金鑰時
    Gemini Flash 補抓隱性建議；LLM 失敗 fail-to-floor。無金鑰（CI）→ floor-only →
    與 W1 行為一致。

    - 合規 → ``answer = draft``、``compliance_status = "passed"``
    - 命中（關鍵字或 LLM 判定）→ ``answer = SAFE_MESSAGE``、``compliance_status = "blocked"``

    最後一律過 :func:`polaris.graph.redaction.redact` 做輸出端機密 / PII 遮罩
    （defense-in-depth；SAFE_MESSAGE 無機密，遮罩為 no-op）。
    """
    final, status = compliance_agent.review(state.get("draft", ""), active_llm())
    final, _ = redact(final)
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
