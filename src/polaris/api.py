"""Thin FastAPI 後端（W4）—— 把既有引擎包成 HTTP 給 R7 前端 / Cloud Run 用。

實作 **R7 開工指南 §2 已公布契約**（`docs/R7_frontend_開工指南.md`）：

- ``GET  /healthz``  → 健康探針（Cloud Run；重用 :func:`polaris.server.health_payload`）
- ``POST /ask``      → 5 節點 workflow：``{query}`` → ``{answer, compliance_status, citations, trace}``
- ``POST /research`` → Deep Research ReAct：``{question}`` → ``{final_answer, evidence, react_steps, status, compliance_status}``

**欄位名一字不差**（``source_id`` / ``compliance_status`` / ``react_steps`` …）；改契約＝R2/R3/R7 一起改。
這層只做「HTTP ↔ 既有函式」的薄轉接：不碰 graph/state/compliance/Deep Research 本體。
無金鑰時引擎走 fallback → 本 API 仍可端到端回應（token-free、CI 可測）。

跑法：``python -m polaris.api``（uvicorn，監聽 ``$PORT``；Cloud Run 會注入）。
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from polaris.graph.deep_research.agent import run_deep_research
from polaris.graph.deep_research.state import ReActStep
from polaris.graph.state import Citation, NodeTrace
from polaris.graph.workflow import build_workflow
from polaris.server import health_payload, resolve_port

app = FastAPI(
    title="Polaris Desk API",
    version="0.1.0",
    description="台股法遵與投研 Agent-Augmented Research Workflow — thin HTTP 後端（W4）",
)


# --- 請求 / 回應模型（回應重用引擎既有 pydantic 型別 → 序列化不會與引擎漂移）---
class AskRequest(BaseModel):
    query: str = Field(min_length=1, description="自然語言問題")


class AskResponse(BaseModel):
    answer: str
    compliance_status: str
    citations: list[Citation]
    trace: list[NodeTrace]


class ResearchRequest(BaseModel):
    question: str = Field(min_length=1, description="開放式研究問題")


class ResearchResponse(BaseModel):
    final_answer: str
    evidence: list[Citation]
    react_steps: list[ReActStep]
    status: str
    compliance_status: str


@app.get("/healthz", tags=["ops"])
def healthz() -> dict[str, str]:
    """Cloud Run 健康探針：證明套件 import + 設定載入（不含祕密）。"""
    return health_payload()


@app.post("/ask", response_model=AskResponse, tags=["research"])
def ask(req: AskRequest) -> AskResponse:
    """跑 5 節點 workflow，回帶引用 + 合規狀態 + 每節點 trace 的答案。"""
    result = build_workflow().invoke({"query": req.query})
    return AskResponse(
        answer=result.get("answer", ""),
        compliance_status=result.get("compliance_status", "unknown"),
        citations=result.get("citations") or [],
        trace=result.get("trace") or [],
    )


@app.post("/research", response_model=ResearchResponse, tags=["research"])
def research(req: ResearchRequest) -> ResearchResponse:
    """跑 Deep Research ReAct loop（≤6 迴圈 / ≥3 引用 / 過合規），回結論 + 證據 + 步驟。"""
    r = run_deep_research(req.question)
    return ResearchResponse(
        final_answer=r.final_answer,
        evidence=r.evidence,
        react_steps=r.react_steps,
        status=r.status,
        compliance_status=r.compliance_status,
    )


def main() -> None:  # pragma: no cover - 進入點，由 `python -m polaris.api` 啟動
    import uvicorn

    port = resolve_port()
    print(f"Polaris Desk API on 0.0.0.0:{port} — POST /ask · POST /research · GET /healthz")
    uvicorn.run(app, host="0.0.0.0", port=port)  # noqa: S104 — 容器內需綁全介面


if __name__ == "__main__":  # pragma: no cover
    main()
