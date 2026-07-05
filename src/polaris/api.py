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

import hashlib
import hmac
import json
import logging
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from polaris.auth import current_user
from polaris.config import settings
from polaris.graph.deep_research.agent import run_deep_research
from polaris.graph.deep_research.state import ReActStep
from polaris.graph.input_gate import screen_query
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
from polaris.ratelimit import RateLimiter
from polaris.server import health_payload, resolve_port
from polaris.structured_store import StructuredStore
from polaris.user_store import UserStore

_log = logging.getLogger(__name__)

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


# --- 輸入上限（security review #3：成本型 DoS / 儲存濫用防護）---
# LLM / 檢索入口的 query / question 字數上限——擋超長輸入觸發 LLM / retrieval 成本。
# 自然語言研究問句 2000 字綽綽有餘；超過由 FastAPI 回 422。
_MAX_QUERY_LEN = 2000
# 歷史紀錄寫入 Firestore 的上限：tickers 筆數、整包 result 的序列化位元組數。
_MAX_TICKERS = 50
_MAX_RESULT_BYTES = 256 * 1024  # 256 KiB：整包 result 還原所需，遠大於正常回應
# 通知事件 payload 序列化上限——擋超大事件灌爆收件匣 / 外送管道（security review #2/#3）。
_MAX_EVENT_BYTES = 64 * 1024  # 64 KiB：真實事件遠小於此（標題 + 證據數筆）
_NOTIFY_TOKEN_HEADER = "X-Polaris-Notify-Token"


# --- 請求 / 回應模型（回應重用引擎既有 pydantic 型別 → 序列化不會與引擎漂移）---
def _reject_blank(value: str) -> str:
    """空白（含全形空白）視同未輸入 → 422，不把垃圾餵進引擎。"""
    if not value.strip():
        raise ValueError("不可為空白")
    return value


def _viewer_for(user: dict | None) -> str:
    """ACL principal 由**已驗證**的 Google 身分（``sub``）推導；匿名 → public sentinel。

    security review #1：``viewer`` 絕不可由 client 提供——否則任何呼叫者只要把
    身分改成 ``owner`` 就能讀他人 owner-scoped 文件（store SQL 以 ``owner == viewer``
    放行）。匿名請求固定看公開文件（owner IS NULL）。
    """
    if user and user.get("sub"):
        return user["sub"]
    return PUBLIC_VIEWER


def require_producer(
    token: str | None = Header(default=None, alias=_NOTIFY_TOKEN_HEADER),
) -> None:
    """通知「生產者」端點守門（security review #2）。

    - 設了 ``notifications_producer_token`` → 一律要求 header 常數時間相符，否則 401。
    - 沒設 + ``app_env=="cloud"`` → fail closed 503：prod 未設定即拒收，絕不接受匿名事件。
    - 沒設 + 非 cloud（local / CI / demo）→ 放行，保 token-free 開發與互動 demo。
    """
    expected = settings.notifications_producer_token
    if not expected:
        if settings.app_env == "cloud":
            raise HTTPException(
                status_code=503,
                detail="通知生產者端點未設定密鑰（NOTIFICATIONS_PRODUCER_TOKEN）",
            )
        return  # 本地 / CI / demo：token-free 放行
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="需要有效的通知生產者密鑰")


# --- /ask /research app 層限流（security review #4：匿名成本型 DoS 護欄）---
# Phase 0 的 internal ingress 擋掉「直連 api」，但擋不到「匿名經 polaris-web 的
# /api/* 代轉」這條——後端 current_user 可選、匿名照樣跑 LLM。這個 guard 補上那 30 分。
# 單一進程內存（見 polaris.ratelimit 的侷限說明）；配合 Cloud Run --max-instances 成本天花板有界。
_RESEARCH_LIMITER = RateLimiter(window_s=60.0)
# L0 每人每日提問配額（input_gate 的一環；成本 / 洗版護欄）。24h 固定視窗、key 依身分分桶。
_DAILY_LIMITER = RateLimiter(window_s=86_400.0)


def _client_key(request: Request) -> str:
    """限流分桶 key：優先 ``X-Forwarded-For`` 最左（真實 client，含經 web 代轉的鏈），
    否則退回 socket 對端 IP。

    ⚠️ XFF 可被偽造；此處作為成本護欄的「分桶」而非身分驗證——目的在配合固定視窗 +
    max-instances 封住匿名濫用的成本天花板，不是防單一攻擊者 IP 輪替。要更嚴可改由
    web proxy 注入一個受信 header（如登入 session id）當 key。
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    client = request.client
    return client.host if client else "unknown"


def enforce_rate_limit(request: Request) -> None:
    """``/ask`` ``/research`` 守門：每 client key 每 60s ≤ ``settings.rate_limit_per_min``。

    僅 ``app_env=="cloud"`` 生效（local / CI / demo 放行，保 token-free）；``rate_limit_per_min<=0``
    亦關閉（escape hatch）。超限 → 429 + ``Retry-After: 60``。
    """
    if settings.app_env != "cloud":
        return
    limit = settings.rate_limit_per_min
    if not _RESEARCH_LIMITER.hit(_client_key(request), limit):
        raise HTTPException(
            status_code=429,
            detail="請求過於頻繁，請稍後再試。",
            headers={"Retry-After": "60"},
        )


def enforce_daily_quota(
    request: Request,
    user=Depends(current_user),
) -> None:
    """``/ask`` ``/research`` 每人每日提問配額（L0；``INPUT_GATE`` 週邊的成本 / 洗版護欄）。

    僅 ``app_env=="cloud"`` 且 ``daily_question_quota>0`` 生效（local / CI / demo 放行、
    設 0 關閉）。分桶 key：登入者用 Google ``sub``；匿名用 client IP（``anon:`` 前綴，
    與登入者分開計數）。超限 → 429 + ``Retry-After: 3600``。
    """
    if settings.app_env != "cloud":
        return
    quota = settings.daily_question_quota
    if quota <= 0:
        return
    viewer = _viewer_for(user)
    key = viewer if viewer != PUBLIC_VIEWER else f"anon:{_client_key(request)}"
    if not _DAILY_LIMITER.hit(key, quota):
        raise HTTPException(
            status_code=429,
            detail="今日提問次數已達上限，請明日再試。",
            headers={"Retry-After": "3600"},
        )


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=_MAX_QUERY_LEN, description="自然語言問題")
    # issue #32 的 ``viewer`` ACL principal **不再由 client 提供**——改由後端從
    # 已驗證的 Google id_token（``sub``）推導（見 :func:`_viewer_for`）。請求帶入的
    # ``viewer`` 一律被 pydantic 當 extra field 忽略，杜絕「改 body 讀他人 owner-scoped
    # 文件」的授權邊界錯置（security review #1）。

    _not_blank = field_validator("query")(_reject_blank)


class AskResponse(BaseModel):
    answer: str
    compliance_status: str
    citations: list[Citation]
    trace: list[NodeTrace]


class ResearchRequest(BaseModel):
    question: str = Field(min_length=1, max_length=_MAX_QUERY_LEN, description="開放式研究問題")
    # ``viewer`` 同 :class:`AskRequest`：後端從登入身分推導，client 帶入一律忽略。

    _not_blank = field_validator("question")(_reject_blank)


class ResearchResponse(BaseModel):
    final_answer: str
    evidence: list[Citation]
    react_steps: list[ReActStep]
    status: str
    compliance_status: str


class ContradictionKpi(BaseModel):
    label: str
    value: str | float | int
    unit: str = ""
    delta: str | None = None
    trend: str | None = None


class ContradictionSummary(BaseModel):
    text: str
    cite: str = ""
    page: str = ""


class ContradictionRequest(BaseModel):
    kpis: list[ContradictionKpi] = Field(default_factory=list)
    summary: list[ContradictionSummary] = Field(default_factory=list)


class ContradictionAlert(BaseModel):
    id: str
    origin: str = "contradiction"
    level: str
    title: str
    summary: str
    source: str
    time: str
    cite_key: str | None = None


class ContradictionResponse(BaseModel):
    alerts: list[ContradictionAlert]


_CONTRADICTION_TOPICS = ("全年", "營收", "毛利率", "營業利益率", "指引", "EPS", "資本支出")
_CONTRADICTORY_QUALIFIERS = (
    ("中段", "以上"),
    ("中段", "至少"),
    ("上修", "下修"),
    ("成長", "衰退"),
    ("增加", "減少"),
)


def _numeric_tokens(text: str) -> set[str]:
    return {m.replace(" ", "") for m in re.findall(r"-?\d+(?:\.\d+)?\s*%?", text)}


def _has_provable_conflict(kpi_text: str, summary_text: str) -> bool:
    for left, right in _CONTRADICTORY_QUALIFIERS:
        if (left in kpi_text and right in summary_text) or (
            right in kpi_text and left in summary_text
        ):
            return True
    kpi_numbers = _numeric_tokens(kpi_text)
    summary_numbers = _numeric_tokens(summary_text)
    return bool(kpi_numbers and summary_numbers and kpi_numbers.isdisjoint(summary_numbers))


def _contradiction_id(kpi: ContradictionKpi, item: ContradictionSummary) -> str:
    digest = hashlib.sha256(f"{kpi.label}|{kpi.value}|{item.cite}|{item.text}".encode()).hexdigest()
    return f"contra-{digest[:12]}"


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
def ask(
    req: AskRequest,
    _rl: None = Depends(enforce_rate_limit),
    _dq: None = Depends(enforce_daily_quota),
    user=Depends(current_user),
) -> AskResponse:
    """跑 5 節點 workflow，回帶引用 + 合規狀態 + 每節點 trace 的答案。

    ``viewer`` 由登入身分（Google ``sub``）推導後透傳進 workflow state（issue #32 /
    security review #1）：retriever 依此做 owner-scoped 過濾。匿名 → 只看公開文件。

    輸入端守門（``INPUT_GATE`` 開時生效）：注入 / 離題的問題直接回固定訊息、**不進
    workflow**（省 LLM / 檢索成本）。flag 關 → :func:`screen_query` 一律放行。
    """
    gate = screen_query(req.query)
    if not gate.allowed:
        return AskResponse(
            answer=gate.message, compliance_status="blocked", citations=[], trace=[]
        )
    viewer = _viewer_for(user)
    result = build_workflow().invoke({"query": req.query, "viewer": viewer})
    return AskResponse(
        answer=result.get("answer", ""),
        compliance_status=result.get("compliance_status", "unknown"),
        citations=result.get("citations") or [],
        trace=result.get("trace") or [],
    )


@app.post("/research", response_model=ResearchResponse, tags=["research"])
def research(
    req: ResearchRequest,
    _rl: None = Depends(enforce_rate_limit),
    _dq: None = Depends(enforce_daily_quota),
    user=Depends(current_user),
) -> ResearchResponse:
    """跑 Deep Research ReAct loop（≤6 迴圈 / ≥3 引用 / 過合規），回結論 + 證據 + 步驟。

    ``viewer`` 由登入身分推導後透傳進 run_deep_research（issue #32 / security review #1）：
    R4 真實 search fn 接入後依此做 owner-scoped 過濾；stub_search 無 owner 欄位，目前為 no-op。

    輸入端守門（``INPUT_GATE`` 開時生效）：注入 / 離題的問題直接回固定訊息、**不進
    ReAct loop**（省 LLM / 檢索成本）。flag 關 → :func:`screen_query` 一律放行。
    """
    gate = screen_query(req.question)
    if not gate.allowed:
        return ResearchResponse(
            final_answer=gate.message,
            evidence=[],
            react_steps=[],
            status="blocked",
            compliance_status="blocked",
        )
    viewer = _viewer_for(user)
    r = run_deep_research(req.question, viewer=viewer)
    return ResearchResponse(
        final_answer=r.final_answer,
        evidence=r.evidence,
        react_steps=r.react_steps,
        status=r.status,
        compliance_status=r.compliance_status,
    )


class SuggestionsResponse(BaseModel):
    """前端 useSuggestions hook 的契約。``source`` 標示問句來源（目前固定
    ``rule`` 規則式精選）；``is_generating=False`` 表示沒有待補的 LLM 升級
    （前端見此即不再 poll），保留欄位供日後接 LLM 動態生成。"""

    suggestions: list[str]
    source: Literal["rule", "llm"] = "rule"
    is_generating: bool = False


# 規則式精選提示問句。皆為「研究 / 比較」型問句，**不含**任何買賣建議
# （NFR-031）。前端在 /research（單檔研究）與 /peer（同業比較）顯示為輸入提示晶片。
_SUGGESTION_PRESETS: dict[str, list[str]] = {
    "research": [
        "台積電 2025Q1 毛利率變化與主要原因？",
        "聯發科最近一季營收年增率表現如何？",
        "鴻海近兩季營業利益率的趨勢？",
        "台積電法說會對先進製程的展望重點？",
        "中華電信最近一季每股盈餘（EPS）變化？",
    ],
    "peer": [
        "比較台積電與聯發科最近兩季毛利率",
        "台積電與聯電的先進製程營收占比差異",
        "比較鴻海與和碩的營業利益率",
        "聯發科與高通的研發費用率比較",
        "比較台積電與三星的資本支出規模",
    ],
}


# P3 接地觸點：/suggestions LLM 動態問句的結果分類（觀測 prod 採用率，對齊 R2/R6）。
SUGG_OUTCOME_LLM = "llm"  # 成功：採用 LLM 生成問句
SUGG_OUTCOME_FALLBACK = "fallback"  # flag 關
SUGG_OUTCOME_NO_KEY = "no_key"  # 無金鑰
SUGG_OUTCOME_LLM_ERROR = "llm_error"  # 生成例外
SUGG_OUTCOME_EMPTY = "empty"  # 解析後無有效問句
SUGG_OUTCOME_COMPLIANCE_REJECTED = "compliance_rejected"  # 含買賣字眼


def _llm_suggestions(mode: str, presets: list[str], *, client) -> tuple[list[str], str]:
    """嘗試用 Gemini Flash 生成動態提示問句（P3 接地觸點）。

    Returns ``(suggestions, outcome)``。任一失敗 → 回 ``(presets, outcome)``，token=0。
    Flag ``SUGGESTIONS_LLM`` 必須為 ``"1"`` 才啟動；預設關。

    刻意**不掛 grounding 閘門**：問句不含事實/數字，無來源可接（P3 反模式提醒）。
    唯一守門是 ``compliance_agent`` 的 NFR-031 買賣紅線。
    """
    from polaris.graph.nodes import compliance_agent as _compliance
    from polaris.graph.prompts import SUGGESTIONS_SYSTEM_PROMPT
    from polaris.retry import call_with_retry

    if os.getenv("SUGGESTIONS_LLM", "0") != "1":
        return presets, SUGG_OUTCOME_FALLBACK

    if client is None:
        _log.info("llm_suggestions outcome=%s", SUGG_OUTCOME_NO_KEY)
        return presets, SUGG_OUTCOME_NO_KEY

    scene = "單檔個股研究" if mode == "research" else "同業比較"
    prompt = f"情境：{scene}。請產生 5 條此情境的研究型提示問句。"
    try:
        raw = call_with_retry(
            lambda: client.generate(prompt, flash=True, system_instruction=SUGGESTIONS_SYSTEM_PROMPT)
        )
    except Exception:  # noqa: BLE001 — 任何生成失敗都退回 presets
        _log.info("llm_suggestions outcome=%s", SUGG_OUTCOME_LLM_ERROR)
        return presets, SUGG_OUTCOME_LLM_ERROR

    lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    if not lines:
        _log.info("llm_suggestions outcome=%s", SUGG_OUTCOME_EMPTY)
        return presets, SUGG_OUTCOME_EMPTY

    # NFR-031：整批問句過 compliance（R7：問句也可能暗示買賣）。
    _, comp = _compliance.review("\n".join(lines), client)
    if comp != "passed":
        _log.info("llm_suggestions outcome=%s", SUGG_OUTCOME_COMPLIANCE_REJECTED)
        return presets, SUGG_OUTCOME_COMPLIANCE_REJECTED

    _log.info("llm_suggestions outcome=%s", SUGG_OUTCOME_LLM)
    return lines[:5], SUGG_OUTCOME_LLM


@app.get("/suggestions", response_model=SuggestionsResponse, tags=["research"])
def suggestions(
    mode: Literal["research", "peer"] = Query(
        default="research", description="提示情境：research（單檔研究）/ peer（同業比較）"
    ),
) -> SuggestionsResponse:
    """回傳輸入提示問句晶片（前端 useSuggestions）。預設規則式精選、token-free，
    無效 ``mode`` 由 FastAPI 回 422。NFR-031：問句皆為研究型，絕無買賣建議。

    Flag ``SUGGESTIONS_LLM=1`` 時改走 Gemini 動態生成（過 compliance 才採用），
    否則 / 失敗一律退回 presets（``source="rule"``）。"""
    from polaris.llm.gemini import active_llm as _active_llm

    presets = _SUGGESTION_PRESETS[mode]
    items, outcome = _llm_suggestions(mode, presets, client=_active_llm())
    if outcome == SUGG_OUTCOME_LLM:
        return SuggestionsResponse(suggestions=items, source="llm")
    return SuggestionsResponse(suggestions=presets, source="rule")


@app.post("/contradiction", response_model=ContradictionResponse, tags=["research"])
def contradiction(req: ContradictionRequest) -> ContradictionResponse:
    """保守比對 KPI 與摘要；只回報可由數字或方向措辭證明的矛盾。"""
    now = datetime.now().strftime("%H:%M")
    alerts: list[ContradictionAlert] = []
    for kpi in req.kpis:
        kpi_text = f"{kpi.label} {kpi.value}{kpi.unit}"
        topics = [topic for topic in _CONTRADICTION_TOPICS if topic in kpi.label]
        for item in req.summary:
            if topics and not any(topic in item.text for topic in topics):
                continue
            if not _has_provable_conflict(kpi_text, item.text):
                continue
            location = " ".join(part for part in (item.cite, item.page) if part)
            alerts.append(
                ContradictionAlert(
                    id=_contradiction_id(kpi, item),
                    level="mid",
                    title=f"{kpi.label}：KPI 與摘要表述不一致",
                    summary=(
                        f"KPI 顯示「{kpi.value}{kpi.unit}」，摘要顯示「{item.text}」；"
                        f"請核對 {location or '引用原文'}。"
                    ),
                    source=f"矛盾偵測 · {item.cite or '未標引用'} vs KPI",
                    time=now,
                    cite_key=item.cite or None,
                )
            )

    if not alerts:
        alerts.append(
            ContradictionAlert(
                id="contra-pass",
                level="info",
                title="交叉比對通過",
                summary="本次 KPI 與摘要未發現可由數字或方向措辭證明的矛盾。",
                source="矛盾偵測引擎",
                time=now,
            )
        )
    return ContradictionResponse(alerts=alerts)


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
def publish_event(event: dict, _=Depends(require_producer)) -> PublishOutcome:
    """發布事件進**真實管線**（去重→接地→合規閘門→訂閱→digest/派送）。

    需內部生產者密鑰（security review #2，見 :func:`require_producer`）。超大 payload
    → 413（擋灌爆收件匣 / 外送）。壞事件回 ``status=rejected``（HTTP 200——拒收是管線
    的正常 outcome，不是傳輸層錯誤；生產者依 ``status`` 分支）。
    """
    size = len(json.dumps(event, ensure_ascii=False, default=str).encode("utf-8"))
    if size > _MAX_EVENT_BYTES:
        raise HTTPException(
            status_code=413, detail=f"事件過大（{size} > {_MAX_EVENT_BYTES} bytes）"
        )
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
def reset_notifications(_=Depends(require_producer)) -> dict[str, str]:
    """重置為全新收件匣（in-memory 單例換新；demo / 測試隔離用）。

    與 ``/events`` 同守門（security review #2）：未授權者不得清空收件匣。cloud 未設密鑰
    時一律 503（prod 本就不該對外開放 reset）。
    """
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
    # 前端顯示用（R3_需求清單_from_R7.md §1）
    title: str = ""
    time: str = ""
    source: str = ""
    origin: str = "research"


@app.get("/alerts", response_model=list[AlertResponse], tags=["watchdog"])
def alerts() -> list[AlertResponse]:
    """跑 mock MOPS 事件集 → WatchdogAlert 陣列（token-free fallback，CI 可測）。

    R7 Alert Inbox 直接消費本端點；severity 上色、blocked 標紅。
    無 Gemini 金鑰時 Watchdog 走確定性 fallback（token=0）。
    """
    events = load_mock_events(_WATCHDOG_MOCK_EVENTS)
    results = []
    for event in events:
        a = run_watchdog(event)
        results.append(AlertResponse(
            event_id=a.event_id,
            ticker=a.ticker,
            summary=a.summary,
            compliance_status=a.compliance_status,
            severity=a.severity,
            evidence=a.evidence,
            title=event.title,
            time=event.published_at.strftime("%H:%M"),
            source=f"MOPS · {event.ticker}",
            origin="research",
        ))
    return results


# --- 結構化資料讀層（polaris_core 直讀，給前端財務卡 / 事件時間軸 / 公司清單）---
#
# 「兩者都要」分層：語意問答走 /ask、/research；結構化表（company_dim /
# financial_metrics / events）由此唯讀端點供給 —— 前端不直連 BQ、不耦合實體 schema。
# StructuredStore 用注入式 client seam（同 BigQueryStore）：lazy 建立，無查詢不連線，
# CI / fallback 不需 GCP 金鑰。

_structured_store = StructuredStore(settings)


class PeriodInfo(BaseModel):
    """期別資訊：period = YYYYQn，has_eps = 是否已公布完整財報。"""

    period: str
    has_eps: bool


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
    metric_name: str | None = None
    value: float | None = None
    unit: str | None = None
    source_id: str | None = None
    published_at: date | None = None
    year: int | None = None
    month: int | None = None


class EventResponse(BaseModel):
    """events 一列（時間軸 / 收件匣；body/raw_json 不在列表回應，需細節再查）。
    欄位已於 2026-06 更名：event_type → event_key，source_name → source_key。
    """

    event_id: str | None = None
    ticker: str | None = None
    event_key: str | None = None
    published_at: date | None = None
    title: str | None = None
    source_url: str | None = None
    source_key: str | None = None


class LibraryDocResponse(BaseModel):
    """文件庫一筆文件（docs/R7_前端_資料表欄位表.md 契約）。"""

    id: str
    ticker: str
    company_name: str = ""
    doc_type: str
    fiscal_period: str = ""
    source_file: str = ""
    page_count: int = 0
    published_at: str = ""
    fetched_at: str = ""
    ingested: bool = True


class LibraryResponse(BaseModel):
    stats: list[dict]
    types: list[dict]
    docs: list[LibraryDocResponse]


_LIB_TYPE_LABELS: dict[str, str] = {
    "major_news":   "重大訊息",
    "transcript":   "法說會逐字稿",
    "earnings_call": "法說會",
    "news":         "新聞",
}


@app.get("/library", response_model=LibraryResponse, tags=["structured"])
def library(
    ticker: str | None = Query(default=None, description="股票代號，如 2330"),
    doc_type: str | None = Query(
        default=None,
        description="文件類型：transcript / major_news / earnings_call",
    ),
    limit: int | None = Query(default=None, ge=1, le=500, description="回傳上限（預設 200）"),
) -> LibraryResponse:
    """文件庫清單：chunks 逐字稿 / 重大訊息 + colpali 法說簡報，文件級 metadata。

    - ``transcript`` / ``major_news`` 來自 ``polaris_core.chunks``（metadata only）。
    - ``earnings_call`` 來自 ``polaris_core.v_colpali_pages_semantic``（source_file 去重）。
    """
    rows = _structured_store.list_library(ticker=ticker, doc_type=doc_type, limit=limit)

    type_counts: dict[str, int] = {}
    for r in rows:
        dt: str = str(r.get("doc_type") or "")
        type_counts[dt] = type_counts.get(dt, 0) + 1

    stats = [{"label": "文件總數", "value": str(len(rows))}]
    types = [
        {"id": k, "label": _LIB_TYPE_LABELS.get(k, k), "count": v}
        for k, v in sorted(type_counts.items())
    ]

    docs = []
    for r in rows:
        d = dict(r)
        for f in ("published_at", "fetched_at"):
            v = d.get(f)
            if v is not None and not isinstance(v, str):
                d[f] = str(v)
        docs.append(LibraryDocResponse(**d))

    return LibraryResponse(stats=stats, types=types, docs=docs)


class ChunkResponse(BaseModel):
    """R7 DocViewer 的引用原文契約。"""

    source_id: str
    title: str
    doc_type: str
    kind_label: str
    ticker: str
    fiscal_period: str | None = None
    published_at: date | None = None
    page: str | None = None
    trust: str = "high"
    content: str
    highlight: str
    hl_tokens: list[str] = Field(default_factory=list)


_DOC_TYPE_LABELS = {
    "transcript": "法說逐字稿",
    "major_news": "重大訊息",
    "news": "新聞",
    "presentation": "法說簡報",
}

# 法說簡報/逐字稿的 chunk_id 內嵌頁碼：{ticker}-{period}-p{page:03d}-c{seq:03d}。
# 新聞 news_<hex> / 重大訊息 mops_<hex> 無頁碼 → 回 None（前端顯示「頁碼未提供」，正確）。
_PAGE_IN_CHUNK_ID_RE = re.compile(r"-p(\d+)-c\d+$")


def _page_label(chunk_id: str | None) -> str | None:
    """從 chunk_id 還原頁碼標籤（issue #83）；無頁碼來源回 None。"""
    m = _PAGE_IN_CHUNK_ID_RE.search(chunk_id or "")
    return f"第 {int(m.group(1))} 頁" if m else None


@app.get("/companies", response_model=list[CompanyResponse], tags=["structured"])
def companies() -> list[CompanyResponse]:
    """canonical 公司清單（company_dim，~20 列）。前端顯示用 ticker→公司名對照。"""
    return [CompanyResponse(**row) for row in _structured_store.list_companies()]


@app.get("/periods", response_model=list[PeriodInfo], tags=["structured"])
def periods() -> list[PeriodInfo]:
    """BQ 中實際存在的 fiscal_period 清單，倒序排列；含 has_eps 旗標供前端標示「已公布財報 / 僅月營收」。"""
    return [PeriodInfo(**row) for row in _structured_store.list_periods()]


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
    type: str | None = Query(  # noqa: A002 — 對齊欄位名 event_key 的對外簡寫
        default=None, description="事件型別（event_key），如 monthly_revenue / earnings_call / major_news / news"
    ),
    limit: int | None = Query(default=None, ge=1, le=1000, description="回傳上限（預設 200）"),
) -> list[EventResponse]:
    """事件流（events），時間倒序，可依 ticker / type 過濾。做公司動態時間軸用。"""
    rows = _structured_store.list_events(ticker=ticker, event_type=type, limit=limit)
    return [EventResponse(**row) for row in rows]


# --- Peer Compare (R7 同業比較) -----------------------------------------------

_VALUATION_METRICS = {"pe_ratio", "pb_ratio", "ps_ratio"}


def _search_peer_calls_in_period(ticker: str, period: str, question: str) -> list[Citation]:
    """單一季別的法說 RAG：優先逐字稿，無逐字稿時退回法說簡報。注入 seam for tests.

    台股多數公司不提供法說逐字稿（目前僅 4/20 家入庫），但全 20 家都有法說簡報
    （presentation）。逐字稿查空時退回簡報，避免那些公司的同業比較回空引用。
    """
    from polaris.retrieval.retriever import make_retriever_search_fn

    for doc_type in ("transcript", "presentation"):
        search = make_retriever_search_fn(
            viewer=PUBLIC_VIEWER,
            filters={"company": ticker, "period": period, "doc_type": doc_type},
        )
        cites = search(question)
        if cites:
            return cites
    return []


def _search_peer_calls(ticker: str, period: str, question: str) -> list[Citation]:
    """法說 RAG：先查請求季，查不到時退回最新『已公布』季再查一次。

    季底剛過的季（如 2026-06 時的 2026Q2）只有月營收 / 重大訊息、**尚無法說**
    （逐字稿 / 簡報都還沒開），但法說質性內容（資本支出指引、產能策略、毛利展望等）
    落在最新已公布季（如 2026Q1）。若不退回，問「2026 資本支出」這類題目時整段
    法說看法會落空（issue：同業比較查不到資本支出）。

    僅在「請求季比最新已公布季新」時退回——避免拿較新季的法說混充某個真的無法說
    的歷史季（那種情況誠實回空）。
    """
    cites = _search_peer_calls_in_period(ticker, period, question)
    if cites:
        return cites

    from polaris.graph.temporal import active_anchor

    anchor = active_anchor()
    if anchor and period > anchor:
        return _search_peer_calls_in_period(ticker, anchor, question)
    return []


class _PeerCitationOut(BaseModel):
    src: str
    page: str


class _PeerMetricSide(BaseModel):
    v: str
    citations: list[_PeerCitationOut]


class _PeerKpi(BaseModel):
    label: str
    a: _PeerMetricSide
    b: _PeerMetricSide
    diff: str
    better: Literal["a", "b"]


class _PeerFinancialRow(BaseModel):
    metric: str
    a: _PeerMetricSide
    b: _PeerMetricSide
    better: Literal["a", "b"]
    note: str


class _PeerCallSide(BaseModel):
    stance: str
    tone: Literal["pos", "neu", "neg"]
    quote: str
    cite: str


class _PeerCall(BaseModel):
    dim: str
    topic: str
    a: _PeerCallSide
    b: _PeerCallSide


class _PeerTrendRow(BaseModel):
    period: str
    metric: str
    a_value: float | None
    b_value: float | None


class _PeerValuationRow(BaseModel):
    metric: str
    a: str
    b: str
    note: str


class PeerCompareRequest(BaseModel):
    a_ticker: str = Field(min_length=1)
    b_ticker: str = Field(min_length=1)
    fiscal_period: str = Field(min_length=1, description="如 2026Q1")
    question: str = Field(min_length=1)
    month: int | None = Field(default=None, ge=1, le=12, description="月份（1-12），null 表示全季")


class PeerCompareResponse(BaseModel):
    a_ticker: str
    b_ticker: str
    fiscal_period: str
    kpis: list[_PeerKpi]
    financial: list[_PeerFinancialRow]
    calls: list[_PeerCall]
    # 法說實際來源季：請求季尚無法說、_search_peer_calls 退回最新已公布季時 ≠ fiscal_period
    # （如請求 2026Q2、法說退回 2026Q1）；與請求季相同或無法說 → None。前端據此明示
    # 「法說看法來自 {calls_period}」，避免使用者誤以為法說也是請求季。
    calls_period: str | None = None
    trend: list[_PeerTrendRow]
    valuation: list[_PeerValuationRow]
    summary: str
    compliance_status: str


def _fmt_value(value: float, unit: str | None) -> str:
    unit = unit or ""
    if unit == "%":
        return f"{value:.2f}%"
    if "千元" in unit:
        yi = value / 100_000
        return f"{yi:.0f} 億" if yi >= 100 else f"{yi:.1f} 億"
    # EPS 等其他單位：固定 2 位小數，不附單位後綴（單位已在 label 顯示）
    return f"{value:.2f}"


# 頂部 KPI 卡片只顯示這幾個核心指標（依優先級排序）
_KPI_PRIORITY = ["eps", "gross_margin", "net_margin", "revenue_yoy", "revenue"]

_PEER_METRIC_LABELS = {
    # 月營收指標（financial_metrics 事實表）
    "revenue":            "月營收",
    "revenue_delta":      "月增額",
    "revenue_prior_year": "去年同期",
    "revenue_yoy":        "月營收 YoY",
    "ytd_revenue":        "累計營收",
    "ytd_delta":          "累計增額",
    "ytd_yoy":            "累計 YoY",
    # 季報損益指標
    "gross_profit":            "毛利額",
    "gross_margin":            "毛利率",
    "operating_expense":       "營業費用",
    "operating_income":        "營業利益",
    "operating_margin":        "營業利益率",
    "pretax_income":           "稅前淨利",
    "net_income":              "淨利",
    "net_margin":              "淨利率",
    "eps":                     "EPS",
    "revenue_q":               "季營收",
    "ytd_revenue_prior_year":  "累計去年同期",
    # 資產負債指標
    "roe":                "ROE",
    "roa":                "ROA",
    "capex":              "資本支出",
    "free_cash_flow":     "自由現金流",
    "debt_ratio":         "負債比率",
    "dividend":           "股利",
    # 估值
    "pe_ratio":           "PE",
    "pb_ratio":           "PB",
    "ps_ratio":           "PS",
}


def _metric_side(row: dict, period: str) -> _PeerMetricSide:
    month = row.get("month")
    page_label = f"{period[:4]}年{month}月" if month else period
    return _PeerMetricSide(
        v=_fmt_value(row["value"], row.get("unit")),
        citations=[
            _PeerCitationOut(src=str(row.get("source_id") or ""), page=page_label)
        ],
    )


def _metric_diff(a_row: dict, b_row: dict) -> tuple[str, Literal["a", "b"]]:
    difference = float(a_row["value"]) - float(b_row["value"])
    unit = a_row.get("unit") or ""
    better: Literal["a", "b"] = "a" if difference >= 0 else "b"
    if unit == "%" and a_row.get("unit") == b_row.get("unit"):
        return f"{abs(difference):.2f}pp", better
    if "千元" in unit:
        yi = abs(difference) / 100_000
        fmt = f"{yi:.0f} 億" if yi >= 100 else f"{yi:.1f} 億"
        return fmt, better
    return f"{abs(difference):.2f}", better


# 法說語氣關鍵詞（描述「發言語氣」而非投資建議——NFR-031 不涉買賣方向）。
_TONE_POSITIVE = (
    "成長", "強勁", "翻倍", "創新高", "看好", "增長", "提升", "樂觀", "擴產",
    "需求強", "上修", "加速", "領先", "動能", "優於", "回升", "新高",
)
_TONE_NEGATIVE = (
    "衰退", "下滑", "疲弱", "保守", "修正", "不確定", "逆風", "壓力", "下修",
    "放緩", "庫存調整", "挑戰", "風險", "低於", "疲軟", "謹慎",
)
_TONE_STANCE = {"pos": "偏正面", "neu": "中性陳述", "neg": "偏保守"}


def _infer_call_tone(snippet: str) -> Literal["pos", "neu", "neg"]:
    """以關鍵詞數判讀法說「發言語氣」；正負相抵或皆無 → 中性。token-free、可測。"""
    text = snippet or ""
    pos = sum(text.count(k) for k in _TONE_POSITIVE)
    neg = sum(text.count(k) for k in _TONE_NEGATIVE)
    if pos > neg:
        return "pos"
    if neg > pos:
        return "neg"
    return "neu"


def _call_side(citation: Citation | None) -> _PeerCallSide:
    if citation is None:
        return _PeerCallSide(stance="資料不足", tone="neu", quote="", cite="")
    tone = _infer_call_tone(citation.snippet)
    return _PeerCallSide(
        stance=_TONE_STANCE[tone],
        tone=tone,
        quote=citation.snippet,
        cite=citation.source_id,
    )


# P1 peer-synthesis outcome constants (R6 採用率可觀測).
PEER_OUTCOME_POLISHED = "polished"
PEER_OUTCOME_GATE_FAILED = "gate_failed"
PEER_OUTCOME_LLM_ERROR = "llm_error"
PEER_OUTCOME_NO_KEY = "no_key"
PEER_OUTCOME_COMPLIANCE_REJECTED = "compliance_rejected"
PEER_OUTCOME_FALLBACK = "fallback"


# 條列前綴（「・」「-」「*」「1.」「1)」「1、」等）：LLM 偶爾仍會自帶；前端
# PeerSummaryPanel 已會渲染項目符號，這裡統一去除，避免雙重 bullet。
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[・·‧•◦\-\*–—]+|\d+[.)、])\s*")


def _bulletize_summary(text: str) -> str:
    """把摘要整理成「每行一個重點、無前綴符號」的條列字串。

    前端 ``PeerSummaryPanel`` 以換行切分並自動加項目符號（第一行視為總覽標題），
    因此這裡只負責：去空行、去每行開頭的條列／編號符號、trim。回傳以 ``\\n`` 連接。
    """
    lines: list[str] = []
    for raw in (text or "").splitlines():
        cleaned = _BULLET_PREFIX_RE.sub("", raw.strip()).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _peer_synthesis(base: str, *, client) -> tuple[str, str]:
    """嘗試用 Gemini Flash 把 peer-compare 確定性摘要潤飾成敘事段落（P1 接地觸點）。

    Returns ``(summary_text, outcome)``。不過閘門 / compliance 失敗 / 例外 → 回 ``(base, outcome)``。
    Flag ``PEER_COMPARE_LLM_SYNTHESIS`` 必須為 ``"1"`` 才啟動；預設關（token=0）。
    """
    import re as _re

    from polaris.graph.deep_research.state import numbers_grounded_in_text
    from polaris.graph.nodes import compliance_agent as _compliance
    from polaris.graph.prompts import PEER_SYNTHESIS_SYSTEM_PROMPT
    from polaris.retry import call_with_retry

    if os.getenv("PEER_COMPARE_LLM_SYNTHESIS", "0") != "1":
        return base, PEER_OUTCOME_FALLBACK

    if client is None:
        _log.info("peer_synthesis outcome=%s", PEER_OUTCOME_NO_KEY)
        return base, PEER_OUTCOME_NO_KEY

    try:
        prose = call_with_retry(
            lambda: client.generate(base, flash=True, system_instruction=PEER_SYNTHESIS_SYSTEM_PROMPT)
        )
    except Exception:  # noqa: BLE001
        _log.info("peer_synthesis outcome=%s", PEER_OUTCOME_LLM_ERROR)
        return base, PEER_OUTCOME_LLM_ERROR

    # Gate 1: prose must contain at least one source tag (來源：...).
    # Gate 2: every number in prose must come from the deterministic base
    # (防幻覺數字；憲法 §II「每個數字都要有來源」)。base 已是接地的數字來源。
    # #56 Option A：放行「經驗證的接地算術」——比較敘事的派生數字（如「高出 X 個
    # 百分點」）若恰等於兩個 base 數字的 ±（重算精確相等）亦視為接地，提高 P1 採用率。
    if not _re.search(r"[（(]來源[：:][^）)]+[）)]", prose) or not numbers_grounded_in_text(
        prose, base, allow_arithmetic=True
    ):
        _log.info("peer_synthesis outcome=%s", PEER_OUTCOME_GATE_FAILED)
        return base, PEER_OUTCOME_GATE_FAILED

    # Compliance check (R7: 比較→買賣 紅線).
    _, comp = _compliance.review(prose, client)
    if comp != "passed":
        _log.info("peer_synthesis outcome=%s", PEER_OUTCOME_COMPLIANCE_REJECTED)
        return base, PEER_OUTCOME_COMPLIANCE_REJECTED

    _log.info("peer_synthesis outcome=%s", PEER_OUTCOME_POLISHED)
    return prose, PEER_OUTCOME_POLISHED


@app.post("/peer-compare", response_model=PeerCompareResponse, tags=["research"])
def peer_compare(req: PeerCompareRequest) -> PeerCompareResponse:
    """同業比較：真實財務指標 + 法說 RAG 引用；PE/PB 目前無資料回 []，不造假。

    輸入端守門只跑**注入層**（``check_scope=False``）：a_ticker / b_ticker 已是 canonical
    標的、天生 in-scope，範圍分類對此無意義且有誤擋風險。``INPUT_GATE_INJECTION`` 關 → 放行。
    """
    gate = screen_query(req.question, check_scope=False)
    if not gate.allowed:
        return PeerCompareResponse(
            a_ticker=req.a_ticker,
            b_ticker=req.b_ticker,
            fiscal_period=req.fiscal_period,
            kpis=[],
            financial=[],
            calls=[],
            trend=[],
            valuation=[],
            summary=gate.message,
            compliance_status="blocked",
        )
    a_rows = _structured_store.list_financials(ticker=req.a_ticker, period=req.fiscal_period)
    b_rows = _structured_store.list_financials(ticker=req.b_ticker, period=req.fiscal_period)

    # 若指定月份，只保留該月的月營收（month == req.month）與不含月份的季度指標（month is None）
    if req.month is not None:
        a_rows = [r for r in a_rows if r.get("month") is None or r.get("month") == req.month]
        b_rows = [r for r in b_rows if r.get("month") is None or r.get("month") == req.month]

    # index by metric_id, exclude valuation metrics (no canonical data yet).
    # 逐列建 dict（取第一筆 = published_at DESC 最新），避免 dict comprehension 取到最舊那筆。
    a_by_metric: dict[str, dict] = {}
    for r in a_rows:
        mid = r.get("metric_id")
        if mid and mid not in _VALUATION_METRICS and mid not in a_by_metric:
            a_by_metric[mid] = r

    b_by_metric: dict[str, dict] = {}
    for r in b_rows:
        mid = r.get("metric_id")
        if mid and mid not in _VALUATION_METRICS and mid not in b_by_metric:
            b_by_metric[mid] = r

    common_metrics = [m for m in a_by_metric if m in b_by_metric]

    # 財務明細表只顯示有意義的指標，排除純衍生計算欄（delta、prior_year 等）
    _FINANCIAL_DISPLAY = {
        "eps", "gross_margin", "net_margin", "operating_margin", "operating_income",
        "gross_profit", "net_income", "revenue_q",
        "revenue", "revenue_yoy", "ytd_revenue", "ytd_yoy",
        "roe", "roa", "capex",
    }

    kpi_map: dict[str, _PeerKpi] = {}
    financial: list[_PeerFinancialRow] = []
    for metric in common_metrics:
        ar = a_by_metric[metric]
        br = b_by_metric[metric]
        a_side = _metric_side(ar, req.fiscal_period)
        b_side = _metric_side(br, req.fiscal_period)
        difference, better = _metric_diff(ar, br)
        label = ar.get("metric_name") or _PEER_METRIC_LABELS.get(metric, metric)
        if metric in _KPI_PRIORITY:
            kpi_map[metric] = _PeerKpi(
                label=label,
                a=a_side,
                b=b_side,
                diff=difference,
                better=better,
            )
        if metric in _FINANCIAL_DISPLAY:
            financial.append(
                _PeerFinancialRow(
                    metric=label,
                    a=a_side,
                    b=b_side,
                    better=better,
                    note=f"差異 {difference}",
                )
            )
    # 依 _KPI_PRIORITY 順序排列，只保留有資料的項目
    kpis = [kpi_map[m] for m in _KPI_PRIORITY if m in kpi_map]

    # law call RAG for both tickers
    a_cites = _search_peer_calls(req.a_ticker, req.fiscal_period, req.question)
    b_cites = _search_peer_calls(req.b_ticker, req.fiscal_period, req.question)

    # 法說退回偵測：_search_peer_calls 在請求季無法說時會退回最新已公布季，引用因此標的
    # 是「實際來源季」而非請求季。若所有法說引用同屬一個 ≠ 請求季的季別 → 標記 calls_period，
    # 讓前端明示「法說看法來自 {calls_period}」（如請求 2026Q2、法說退回 2026Q1）。
    call_periods = {c.fiscal_period for c in (*a_cites, *b_cites) if c.fiscal_period}
    calls_period = (
        next(iter(call_periods))
        if len(call_periods) == 1 and req.fiscal_period not in call_periods
        else None
    )

    calls: list[_PeerCall] = []
    for index in range(max(len(a_cites), len(b_cites))):
        ac = a_cites[index] if index < len(a_cites) else None
        bc = b_cites[index] if index < len(b_cites) else None
        calls.append(
            _PeerCall(
                dim="法說會",
                topic=req.question,
                a=_call_side(ac),
                b=_call_side(bc),
            )
        )

    # trend: all periods for common metrics in fiscal data (all periods, not just requested)
    # 只顯示最具代表性的趨勢指標，避免 8 種 revenue 子指標全部展出
    _TREND_METRICS = {"revenue_yoy", "revenue"}
    a_all = _structured_store.list_financials(ticker=req.a_ticker)
    b_all = _structured_store.list_financials(ticker=req.b_ticker)
    # 用 loop 取第一筆（published_at DESC = 最新），與 a_by_metric 邏輯一致，避免 dict comprehension 取到最舊
    a_all_idx: dict[tuple[str, str], dict] = {}
    for r in a_all:
        key = (r["fiscal_period"], r["metric_id"])
        if r["metric_id"] not in _VALUATION_METRICS and key not in a_all_idx:
            a_all_idx[key] = r
    b_all_idx: dict[tuple[str, str], dict] = {}
    for r in b_all:
        key = (r["fiscal_period"], r["metric_id"])
        if r["metric_id"] not in _VALUATION_METRICS and key not in b_all_idx:
            b_all_idx[key] = r

    # only include metrics with data in more than one period (i.e. actual trend)
    a_metric_periods: dict[str, set[str]] = {}
    for (period, metric), _ in a_all_idx.items():
        a_metric_periods.setdefault(metric, set()).add(period)

    trend_keys: set[tuple[str, str]] = set()
    for (period, metric) in a_all_idx:
        if (
            (period, metric) in b_all_idx
            and metric in _TREND_METRICS
            and len(a_metric_periods.get(metric, set())) > 1
        ):
            trend_keys.add((period, metric))

    trend: list[_PeerTrendRow] = sorted(
        [
            _PeerTrendRow(
                period=period,
                metric=a_all_idx[(period, metric)].get("metric_name") or _PEER_METRIC_LABELS.get(metric, metric),
                a_value=a_all_idx[(period, metric)]["value"],
                b_value=b_all_idx[(period, metric)]["value"],
            )
            for period, metric in trend_keys
        ],
        key=lambda r: (r.period, r.metric),
    )

    # build summary：條列格式，第一行為總覽標題，其後每行一個比較重點，不在句中暴露
    # source_id。每行「不」自帶「・」前綴——前端 PeerSummaryPanel 會自動加項目符號。
    summary_parts = [f"比較期間 {req.fiscal_period}，{req.a_ticker} 與 {req.b_ticker} 主要指標對比："]
    for kpi in kpis:
        better_name = req.a_ticker if kpi.better == "a" else req.b_ticker
        summary_parts.append(
            f"{kpi.label}：{req.a_ticker} {kpi.a.v} vs {req.b_ticker} {kpi.b.v}"
            f"（{better_name} 領先 {kpi.diff}）"
        )
    # 法說質性節錄：每家取首筆引用，讓 fallback（無 LLM）摘要也帶「看法」而非純數字。
    for ticker, side in ((req.a_ticker, "a"), (req.b_ticker, "b")):
        quote = next(
            (getattr(c, side).quote for c in calls if getattr(c, side).quote), ""
        )
        if quote:
            summary_parts.append(f"{ticker} 法說重點：{quote[:120]}")
    raw_summary = "\n".join(summary_parts)

    # LLM 生成自然語言摘要（有 GEMINI_API_KEY 才呼叫；否則沿用結構化字串）。
    # 觸發條件：有財務指標「或」有法說引用——後者讓「對 AI 需求的看法」這類純質性
    # 問題（可能無共同財務指標）也能合成看法，而非掉回單一標題行。
    from polaris.llm.gemini import active_llm

    has_call_quotes = any(c.a.quote or c.b.quote for c in calls)
    llm = active_llm()
    if llm and (kpis or has_call_quotes):
        kpi_lines = "\n".join(
            f"  ・{k.label}：{req.a_ticker} {k.a.v} vs {req.b_ticker} {k.b.v}"
            f"（{req.a_ticker if k.better == 'a' else req.b_ticker} 領先 {k.diff}）"
            for k in kpis
        ) or "（無共同財務指標）"
        call_snippets = [
            f"  ・{req.a_ticker}：{c.a.quote[:300]}"
            for c in calls[:5]
            if c.a.quote
        ] + [
            f"  ・{req.b_ticker}：{c.b.quote[:300]}"
            for c in calls[:5]
            if c.b.quote
        ]
        call_lines = "\n".join(call_snippets[:8]) or "（無法說引用）"
        prompt = (
            f"你是台股產業研究員。請用繁體中文，聚焦回答『使用者問題』，"
            f"為「{req.a_ticker} vs {req.b_ticker}」（{req.fiscal_period}）寫一份同業比較摘要。\n\n"
            f"撰寫原則：以下方『法說引用』為主軸，先合成兩家對使用者問題的看法／立場差異，"
            f"財務數字僅作輔助佐證，不要只堆財務數字。\n\n"
            f"輸出格式（務必嚴格遵守）：\n"
            f"第一行：一句 15-40 字的整體總覽，直接點出兩家對使用者問題看法的最關鍵差異。\n"
            f"接著各一行：分別陳述 {req.a_ticker}、{req.b_ticker} 對使用者問題的看法／立場"
            f"（依法說引用，每行 15-50 字）。\n"
            f"最後 1-2 行：以關鍵財務數字佐證差異（數字需與下列財務指標一致；無指標則省略）。\n"
            f"每行「不要」加「・」「-」「*」等符號或數字編號（介面會自動加項目符號），"
            f"行與行之間用換行分隔，讓使用者一眼就能掃讀。\n\n"
            f"財務指標：\n{kpi_lines}\n\n"
            f"法說引用（節錄）：\n{call_lines}\n\n"
            f"使用者問題：{req.question}\n\n"
            f"限制：禁止出現買進、賣出、建議投資等語句。"
        )
        try:
            llm_summary = _bulletize_summary(llm.generate(prompt, flash=True))
            # 至少要 2 行（總覽＋1 重點）才採用 LLM 版；若 LLM 仍回單段落，
            # 沿用上方結構化條列，確保前端永遠能渲染成 bullet point。
            if "\n" in llm_summary:
                raw_summary = llm_summary
        except Exception:
            pass  # fallback to machine-generated summary

    # P1 接地觸點：flag 開時嘗試 Gemini 潤飾比較結論；fallback = raw_summary。
    from polaris.llm.gemini import active_llm as _active_llm

    final_summary, _ = _peer_synthesis(raw_summary, client=_active_llm())

    from polaris.graph.nodes import compliance_agent

    _, compliance_status = compliance_agent.review(final_summary, None)

    return PeerCompareResponse(
        a_ticker=req.a_ticker,
        b_ticker=req.b_ticker,
        fiscal_period=req.fiscal_period,
        kpis=kpis,
        financial=financial,
        calls=calls,
        calls_period=calls_period,
        trend=trend,
        valuation=[],
        summary=final_summary,
        compliance_status=compliance_status,
    )


@app.get("/chunk/{source_id}", response_model=ChunkResponse, tags=["research"])
def chunk(
    source_id: str,
    user=Depends(current_user),
) -> ChunkResponse:
    """展開單一引用原文；不存在與無權限皆回 404，避免洩漏文件是否存在。

    ``viewer`` 由登入身分推導（security review #1）：匿名只看公開原文，登入者另可
    看自己 owner-scoped 的原文——絕不接受 client 指定 viewer。
    """
    viewer = _viewer_for(user)
    row = _structured_store.get_chunk(source_id, viewer=viewer)
    if row is None:
        raise HTTPException(status_code=404, detail="查無此引用")

    doc_type = row.get("doc_type") or "unknown"
    kind_label = _DOC_TYPE_LABELS.get(doc_type, doc_type)
    ticker = row.get("ticker") or ""
    fiscal_period = row.get("fiscal_period")
    title_parts = [ticker, fiscal_period, kind_label]
    title = "_".join(part for part in title_parts if part)
    content = row.get("chunk_text") or ""
    return ChunkResponse(
        source_id=row.get("chunk_id") or source_id,
        title=title,
        doc_type=doc_type,
        kind_label=kind_label,
        ticker=ticker,
        fiscal_period=fiscal_period,
        published_at=row.get("published_at"),
        page=_page_label(row.get("chunk_id") or source_id),
        content=content,
        highlight=content,
    )


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
    """一筆活動紀錄（B 級：``result`` 存整包 → 日後完整還原）。

    security review #3：登入後寫入 Firestore，需設上限擋儲存濫用——``query`` 字數、
    ``tickers`` 筆數、整包 ``result`` 的序列化大小皆有界。
    """

    origin: str = Field(max_length=32, description='來源頁面："research" | "peer"')
    query: str = Field(min_length=1, max_length=_MAX_QUERY_LEN, description="使用者查詢文字")
    tickers: list[str] = Field(
        default_factory=list, max_length=_MAX_TICKERS, description="涉及股票代號"
    )
    result: dict | None = Field(default=None, description="整包回應，供完整還原（B 級）")

    _not_blank = field_validator("query")(_reject_blank)

    @field_validator("result")
    @classmethod
    def _result_within_limit(cls, value: dict | None) -> dict | None:
        """整包 ``result`` 序列化後不得超過上限——擋大型 JSON 灌進 Firestore。"""
        if value is None:
            return value
        size = len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        if size > _MAX_RESULT_BYTES:
            raise ValueError(f"result 過大（{size} > {_MAX_RESULT_BYTES} bytes）")
        return value


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


@app.delete("/history/{session_id}", tags=["user"])
def delete_history_one(session_id: str, user=Depends(current_user)) -> dict[str, str]:
    """刪除登入使用者一筆活動紀錄（security review #4）；查無 → 404。

    需登入：以 Google ``sub`` 收斂只能刪自己的紀錄。前端原本因後端缺此端點而「靜默
    成功」，導致 Firestore 仍留資料——補上後刪除才真的落地。
    """
    if not _user_store.delete_session(_require_uid(user), session_id):
        raise HTTPException(status_code=404, detail="查無此紀錄")
    return {"status": "deleted"}


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
