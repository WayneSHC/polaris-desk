"""Thin FastAPI 後端（W4）—— 把既有引擎包成 HTTP 給 R7 前端 / Cloud Run 用。

實作 **R7 開工指南 §2 已公布契約**（`docs/R7_frontend_開工指南.md`）：

- ``GET  /healthz``  → 健康探針（Cloud Run；重用 :func:`polaris.server.health_payload`）
- ``POST /ask``      → 5 節點 workflow：``{query}`` → ``{answer, compliance_status, citations, trace}``
- ``POST /research`` → Deep Research ReAct：``{question}`` → ``{final_answer, evidence, react_steps, status, compliance_status}``

通知中心（specs/002，R7 Alert Inbox 升級版的後端契約 + 互動 demo）：

- ``GET  /notifications``               → 收件匣列表 + 未讀數（query: ``ticker`` / ``type``）
- ``POST /notifications/events``        → 發布事件進真實管線，回 ``PublishOutcome``
- ``POST /notifications/{id}/read``     → 標已讀
- ``POST /notifications/reset``         → 重置收件匣（demo / 測試隔離用）
- ``GET  /demo/notifications``          → 互動 demo 頁（單檔 HTML，吃上面四個端點）

Watchdog（specs/003，R7 Alert Inbox 消費端）：

- ``GET  /alerts``                      → mock MOPS 事件跑 Watchdog，回 WatchdogAlert 陣列（token-free）

結構化資料讀層（polaris_core 直讀；前端財務卡 / 事件時間軸 / 公司清單）：

- ``GET  /companies``                   → company_dim（ticker→公司/產業）
- ``GET  /financials``                  → financial_metrics（query: ``ticker`` / ``period`` / ``metric`` / ``limit``）
- ``GET  /events``                      → events 時間流（query: ``ticker`` / ``type`` / ``limit``）

**欄位名一字不差**（``source_id`` / ``compliance_status`` / ``react_steps`` …）；改契約＝R2/R3/R7 一起改。
這層只做「HTTP ↔ 既有函式」的薄轉接：不碰 graph/state/compliance/Deep Research 本體。
無金鑰時引擎走 fallback → 本 API 仍可端到端回應（token-free、CI 可測）。

跑法：``python -m polaris.api``（uvicorn，監聽 ``$PORT``；Cloud Run 會注入）。
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from polaris.auth import current_user
from polaris.config import settings
from polaris.graph.deep_research.agent import run_deep_research
from polaris.graph.deep_research.state import ReActStep
from polaris.graph.state import Citation, NodeTrace
from polaris.graph.watchdog import load_mock_events, run_watchdog
from polaris.graph.workflow import build_workflow
from polaris.retrieval.retriever import PUBLIC_VIEWER
from polaris.notifications import (
    Notification,
    NotificationService,
    PublishOutcome,
    SlackWebhookChannel,
)
from polaris.server import health_payload, resolve_port
from polaris.structured_store import StructuredStore
from polaris.user_store import UserStore

_WATCHDOG_MOCK_EVENTS = (
    Path(__file__).resolve().parent / "graph" / "watchdog" / "data" / "watchdog_events.json"
)

app = FastAPI(
    title="Polaris Desk API",
    version="0.1.0",
    description="台股法遵與投研 Agent-Augmented Research Workflow — thin HTTP 後端（W4）",
)


def _parse_origins(raw: str) -> list[str]:
    """逗號分隔的 CORS 來源字串 → 清單（strip + 去空）。"""
    return [o.strip() for o in raw.split(",") if o.strip()]


# R7 前端（Vercel）跨域呼叫本 API → 需 CORS allowlist（secure-by-default，非萬用 *）。
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_origins(settings.cors_origins),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --- 請求 / 回應模型（回應重用引擎既有 pydantic 型別 → 序列化不會與引擎漂移）---
def _reject_blank(value: str) -> str:
    """空白（含全形空白）視同未輸入 → 422，不把垃圾餵進引擎。"""
    if not value.strip():
        raise ValueError("不可為空白")
    return value


class AskRequest(BaseModel):
    query: str = Field(min_length=1, description="自然語言問題")
    # issue #32: viewer identity for owner-based document access control.
    # Omit to use the public sentinel principal (public docs only).
    viewer: str = Field(default=PUBLIC_VIEWER, description="存取控制身分（issue #32）")

    _not_blank = field_validator("query")(_reject_blank)


class AskResponse(BaseModel):
    answer: str
    compliance_status: str
    citations: list[Citation]
    trace: list[NodeTrace]


class ResearchRequest(BaseModel):
    question: str = Field(min_length=1, description="開放式研究問題")
    # issue #32: viewer identity forwarded to Deep Research search fn.
    viewer: str = Field(default=PUBLIC_VIEWER, description="存取控制身分（issue #32）")

    _not_blank = field_validator("question")(_reject_blank)


class ResearchResponse(BaseModel):
    final_answer: str
    evidence: list[Citation]
    react_steps: list[ReActStep]
    status: str
    compliance_status: str


@app.get("/healthz", tags=["ops"])
@app.get("/health", tags=["ops"])
def healthz() -> dict[str, str]:
    """健康探針：證明套件 import + 設定載入（不含祕密）。

    暴露兩條路徑：``/healthz``（本地 / in-process）與 ``/health``。Cloud Run 的
    Google Front End 會**攔截 `/healthz`**（在抵達容器前回自家 404），故雲端可達的
    探針走 ``/health``（runbook §5）。
    """
    return health_payload()


@app.post("/ask", response_model=AskResponse, tags=["research"])
def ask(req: AskRequest) -> AskResponse:
    """跑 5 節點 workflow，回帶引用 + 合規狀態 + 每節點 trace 的答案。

    ``viewer`` 透傳進 workflow state（issue #32）：retriever 依此做 owner-scoped 過濾。
    """
    result = build_workflow().invoke({"query": req.query, "viewer": req.viewer})
    return AskResponse(
        answer=result.get("answer", ""),
        compliance_status=result.get("compliance_status", "unknown"),
        citations=result.get("citations") or [],
        trace=result.get("trace") or [],
    )


@app.post("/research", response_model=ResearchResponse, tags=["research"])
def research(req: ResearchRequest) -> ResearchResponse:
    """跑 Deep Research ReAct loop（≤6 迴圈 / ≥3 引用 / 過合規），回結論 + 證據 + 步驟。

    ``viewer`` 透傳進 run_deep_research（issue #32）：R4 真實 search fn 接入後
    可依此做 owner-scoped 過濾；stub_search 無 owner 欄位，目前為 no-op。
    """
    r = run_deep_research(req.question, viewer=req.viewer)
    return ResearchResponse(
        final_answer=r.final_answer,
        evidence=r.evidence,
        react_steps=r.react_steps,
        status=r.status,
        compliance_status=r.compliance_status,
    )


# --- 通知中心（specs/002）— thin 轉接到 NotificationService ------------------
#
# Phase 1 收件匣為 in-memory（spec Assumptions；BigQuery 持久化 = Phase 2 / PRD
# OQ-1）→ process 內單例。reset 端點供 demo / 測試取得乾淨狀態。

_DEMO_HTML = Path(__file__).parent / "notifications" / "demo.html"


def _new_notification_service() -> NotificationService:
    return NotificationService(
        channels=[SlackWebhookChannel(settings.slack_webhook_url)],
    )


_notification_service = _new_notification_service()


class NotificationListResponse(BaseModel):
    items: list[Notification]
    unread_count: int
    delivery_failures: list[str]


@app.get("/notifications", response_model=NotificationListResponse, tags=["notifications"])
def list_notifications(
    ticker: str | None = None, type: str | None = None  # noqa: A002 — 對齊契約欄位名
) -> NotificationListResponse:
    """收件匣列表（created_at 倒序）+ 未讀數 + 外送降級記錄。"""
    inbox = _notification_service.inbox
    return NotificationListResponse(
        items=inbox.list(ticker=ticker, type=type),  # type: ignore[arg-type] — 未知 type 僅比對不中
        unread_count=inbox.unread_count(),
        delivery_failures=list(inbox.delivery_failures),
    )


@app.post("/notifications/events", response_model=PublishOutcome, tags=["notifications"])
def publish_event(event: dict) -> PublishOutcome:
    """發布事件進**真實管線**（去重→接地→合規閘門→訂閱→digest/派送）。

    壞事件回 ``status=rejected``（HTTP 200——拒收是管線的正常 outcome，
    不是傳輸層錯誤；生產者依 ``status`` 分支）。
    """
    return _notification_service.publish(event)


@app.post("/notifications/{notification_id}/read", response_model=Notification,
          tags=["notifications"])
def mark_notification_read(notification_id: str) -> Notification:
    """標已讀；查無該通知 → 404。``read_at`` 取 API 邊界當下時間
    （確定性約束只管管線內部；牆鐘是邊界輸入，同事件 ``occurred_at`` 的角色）。"""
    updated = _notification_service.inbox.mark_read(notification_id, at=datetime.now())
    if updated is None:
        raise HTTPException(status_code=404, detail=f"notification not found: {notification_id}")
    return updated


@app.post("/notifications/reset", tags=["notifications"])
def reset_notifications() -> dict[str, str]:
    """重置為全新收件匣（in-memory 單例換新；demo / 測試隔離用）。"""
    global _notification_service
    _notification_service = _new_notification_service()
    return {"status": "reset"}


@app.get("/demo/notifications", response_class=HTMLResponse, tags=["notifications"])
def notifications_demo() -> HTMLResponse:
    """互動 demo 頁：收件匣 UI/UX + 事件模擬器（吃同源 /notifications 端點）。"""
    return HTMLResponse(_DEMO_HTML.read_text(encoding="utf-8"))


# --- Watchdog（specs/003）— R7 Alert Inbox 消費端 ----------------------------

class AlertResponse(BaseModel):
    """R7 Alert Inbox 契約（docs/R7_frontend_開工指南.md §2c）。欄位名一字不差。"""

    event_id: str
    ticker: str
    summary: str
    compliance_status: str
    severity: str
    evidence: list[Citation]


@app.get("/alerts", response_model=list[AlertResponse], tags=["watchdog"])
def alerts() -> list[AlertResponse]:
    """跑 mock MOPS 事件集 → WatchdogAlert 陣列（token-free fallback，CI 可測）。

    R7 Alert Inbox 直接消費本端點；severity 上色、blocked 標紅。
    無 Gemini 金鑰時 Watchdog 走確定性 fallback（token=0）。
    """
    return [
        AlertResponse(
            event_id=a.event_id,
            ticker=a.ticker,
            summary=a.summary,
            compliance_status=a.compliance_status,
            severity=a.severity,
            evidence=a.evidence,
        )
        for a in (run_watchdog(e) for e in load_mock_events(_WATCHDOG_MOCK_EVENTS))
    ]


# --- 結構化資料讀層（polaris_core 直讀，給前端財務卡 / 事件時間軸 / 公司清單）---
#
# 「兩者都要」分層：語意問答走 /ask、/research；結構化表（company_dim /
# financial_metrics / events）由此唯讀端點供給 —— 前端不直連 BQ、不耦合實體 schema。
# StructuredStore 用注入式 client seam（同 BigQueryStore）：lazy 建立，無查詢不連線，
# CI / fallback 不需 GCP 金鑰。

_structured_store = StructuredStore(settings)


class CompanyResponse(BaseModel):
    """company_dim 一列（ticker→公司/產業，join key=ticker）。"""

    ticker: str
    company_name: str | None = None
    english_name: str | None = None
    market: str | None = None
    industry_id: str | None = None
    industry_name: str | None = None
    is_financial: bool | None = None
    aliases: str | None = None


class FinancialMetricResponse(BaseModel):
    """financial_metrics 一列（複合 key：ticker + fiscal_period + metric_id）。"""

    ticker: str | None = None
    fiscal_period: str | None = None
    metric_id: str | None = None
    value: float | None = None
    unit: str | None = None
    source_id: str | None = None
    published_at: date | None = None


class EventResponse(BaseModel):
    """events 一列（時間軸 / 收件匣；body/raw_json 不在列表回應，需細節再查）。"""

    event_id: str | None = None
    ticker: str | None = None
    event_type: str | None = None
    published_at: date | None = None
    title: str | None = None
    source_url: str | None = None


@app.get("/companies", response_model=list[CompanyResponse], tags=["structured"])
def companies() -> list[CompanyResponse]:
    """canonical 公司清單（company_dim，~20 列）。前端顯示用 ticker→公司名對照。"""
    return [CompanyResponse(**row) for row in _structured_store.list_companies()]


@app.get("/financials", response_model=list[FinancialMetricResponse], tags=["structured"])
def financials(
    ticker: str | None = Query(default=None, description="股票代號，如 2330"),
    period: str | None = Query(default=None, description="財報期別，如 2025Q4"),
    metric: str | None = Query(default=None, description="指標代碼，如 revenue / eps"),
    limit: int | None = Query(default=None, ge=1, le=1000, description="回傳上限（預設 200）"),
) -> list[FinancialMetricResponse]:
    """財務指標（financial_metrics），可依 ticker / period / metric 過濾，時間倒序。"""
    rows = _structured_store.list_financials(
        ticker=ticker, period=period, metric=metric, limit=limit
    )
    return [FinancialMetricResponse(**row) for row in rows]


@app.get("/events", response_model=list[EventResponse], tags=["structured"])
def events(
    ticker: str | None = Query(default=None, description="股票代號，如 2330"),
    type: str | None = Query(  # noqa: A002 — 對齊欄位名 event_type 的對外簡寫
        default=None, description="事件型別，如 monthly_revenue / earnings_call"
    ),
    limit: int | None = Query(default=None, ge=1, le=1000, description="回傳上限（預設 200）"),
) -> list[EventResponse]:
    """事件流（events），時間倒序，可依 ticker / type 過濾。做公司動態時間軸用。"""
    rows = _structured_store.list_events(ticker=ticker, event_type=type, limit=limit)
    return [EventResponse(**row) for row in rows]


# --- 使用者活動紀錄 + 訂閱（R7-1：Google OAuth 登入後；Firestore）---------------
#
# 需登入（Bearer Google id_token）：匿名（無 token）一律 401——個人資料不對匿名開放。
# 匿名降級走前端 localStorage（保斷網備援），不打這些端點。UserStore 同樣用注入式
# client seam（lazy Firestore，CI 不連 GCP）。詳見
# docs/cross-role-collab/Auth-Firestore_串接指南_R2決議.md。

_user_store = UserStore(settings)


def _require_uid(user: dict | None) -> str:
    """登入 → 回 Google sub（使用者主鍵）；匿名 → 401。"""
    if not user or not user.get("sub"):
        raise HTTPException(status_code=401, detail="需要登入")
    return user["sub"]


class HistoryIn(BaseModel):
    """一筆活動紀錄（B 級：``result`` 存整包 → 日後完整還原）。"""

    origin: str = Field(description='來源頁面："research" | "peer"')
    query: str = Field(min_length=1, description="使用者查詢文字")
    tickers: list[str] = Field(default_factory=list, description="涉及股票代號")
    result: dict | None = Field(default=None, description="整包回應，供完整還原（B 級）")

    _not_blank = field_validator("query")(_reject_blank)


class HistoryRecordResponse(BaseModel):
    record_id: str
    status: str


class SubsIn(BaseModel):
    tickers: list[str] = Field(default_factory=list, description="訂閱股票代號清單")


class SubsResponse(BaseModel):
    status: str
    tickers: list[str]


@app.post("/history", response_model=HistoryRecordResponse, tags=["user"])
def post_history(body: HistoryIn, user=Depends(current_user)) -> HistoryRecordResponse:
    """存一筆活動紀錄到登入使用者的 Firestore session 集合。"""
    rid = _user_store.save_session(_require_uid(user), body.model_dump())
    return HistoryRecordResponse(record_id=rid, status="ok")


@app.get("/history", tags=["user"])
def get_history(user=Depends(current_user)) -> list[dict]:
    """登入使用者的活動紀錄清單（created_at 倒序）。"""
    return _user_store.list_sessions(_require_uid(user))


@app.get("/history/{session_id}", tags=["user"])
def get_history_one(session_id: str, user=Depends(current_user)) -> dict:
    """單筆紀錄（含整包 ``result``）供前端完整還原；查無 → 404。"""
    s = _user_store.get_session(_require_uid(user), session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="查無此紀錄")
    return s


@app.get("/subscriptions", response_model=SubsResponse, tags=["user"])
def get_subscriptions(user=Depends(current_user)) -> SubsResponse:
    """登入使用者的訂閱清單。"""
    uid = _require_uid(user)
    return SubsResponse(status="ok", tickers=_user_store.get_subs(uid))


@app.post("/subscriptions", response_model=SubsResponse, tags=["user"])
def post_subscriptions(body: SubsIn, user=Depends(current_user)) -> SubsResponse:
    """覆蓋登入使用者的訂閱清單。"""
    uid = _require_uid(user)
    _user_store.set_subs(uid, body.tickers)
    return SubsResponse(status="ok", tickers=body.tickers)


def main() -> None:  # pragma: no cover - 進入點，由 `python -m polaris.api` 啟動
    import uvicorn

    port = resolve_port()
    print(f"Polaris Desk API on 0.0.0.0:{port} — POST /ask · POST /research · GET /healthz")
    uvicorn.run(app, host="0.0.0.0", port=port)  # noqa: S104 — 容器內需綁全介面


if __name__ == "__main__":  # pragma: no cover
    main()
