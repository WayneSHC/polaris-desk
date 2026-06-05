"""polaris.api — thin FastAPI 後端（W4 / R7 Vercel 對接）。

實作 R7 開工指南 §2 已公布契約：GET /healthz、POST /ask、POST /research。
**欄位名一字不差**（source_id / compliance_status / react_steps …）——R7 直接拿 mock
換真後端、零重工。token-free：fallback 模式（無 Gemini 金鑰）即可端到端驗。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from polaris.api import app

VALID_COMPLIANCE = {"passed", "blocked", "unknown"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestHealthz:
    def test_healthz_returns_200_ok(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestAsk:
    def test_ask_returns_contract_shape(self, client):
        r = client.post("/ask", json={"query": "台積電 2025Q1 毛利率如何？"})
        assert r.status_code == 200
        body = r.json()
        # 契約欄位（R7 §2a）：一字不差
        assert set(("answer", "compliance_status", "citations", "trace")) <= body.keys()
        assert isinstance(body["answer"], str) and body["answer"]
        assert body["compliance_status"] in VALID_COMPLIANCE
        assert isinstance(body["citations"], list)
        assert isinstance(body["trace"], list)

    def test_ask_citations_have_contract_fields(self, client):
        r = client.post("/ask", json={"query": "台積電最近兩季營收"})
        for c in r.json()["citations"]:
            assert set(("source_id", "snippet", "origin")) <= c.keys()

    def test_ask_trace_reflects_five_nodes(self, client):
        # 5 節點 workflow trace 不變量：每筆 trace 有 node_name/status
        trace = client.post("/ask", json={"query": "台積電 2025Q1 營收"}).json()["trace"]
        for t in trace:
            assert "node_name" in t and "status" in t

    def test_ask_missing_query_is_422(self, client):
        assert client.post("/ask", json={}).status_code == 422


class TestResearch:
    def test_research_returns_contract_shape(self, client):
        r = client.post(
            "/research",
            json={"question": "比較台積電與聯發科最近兩季毛利率變化"},
        )
        assert r.status_code == 200
        body = r.json()
        # 契約欄位（R7 §2b）：一字不差
        assert set(
            ("final_answer", "evidence", "react_steps", "status", "compliance_status")
        ) <= body.keys()
        assert isinstance(body["final_answer"], str)
        assert body["status"] in {"answered", "exhausted"}
        assert body["compliance_status"] in VALID_COMPLIANCE
        assert isinstance(body["evidence"], list)
        assert isinstance(body["react_steps"], list)

    def test_research_steps_have_thought_and_action(self, client):
        steps = client.post(
            "/research", json={"question": "台積電最近一季風險"}
        ).json()["react_steps"]
        for s in steps:
            assert "thought" in s and "action" in s

    def test_research_missing_question_is_422(self, client):
        assert client.post("/research", json={}).status_code == 422


class TestRouting:
    def test_unknown_path_404(self, client):
        assert client.get("/definitely-not-a-route").status_code == 404
