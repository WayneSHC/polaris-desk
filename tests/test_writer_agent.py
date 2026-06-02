"""D3 — Writer Agent v0：contexts → draft + citations。

- build_citations：把 retriever 的 contexts 轉成 Citation（接地）。
- LLM 路徑 / fallback 兩條都確定性可測。
- NFR-031：即使 LLM 產生買賣建議，下游 Compliance 仍須攔下（端到端驗證）。
"""
from __future__ import annotations

from polaris.graph.nodes import writer_agent as wa
from polaris.graph.state import Citation


SAMPLE_CONTEXTS = [
    {"source_id": "doc-1", "text": "台積電 2025Q1 營收 8,000 億元。"},
    {"source_id": "doc-2", "text": "毛利率約 58%。"},
]


class TestBuildCitations:
    def test_maps_contexts_to_citations(self):
        cites = wa.build_citations(SAMPLE_CONTEXTS)
        assert len(cites) == 2
        assert all(isinstance(c, Citation) for c in cites)
        assert cites[0].source_id == "doc-1"
        assert cites[0].snippet == "台積電 2025Q1 營收 8,000 億元。"

    def test_empty_contexts_yields_no_citations(self):
        assert wa.build_citations([]) == []

    def test_default_origin_is_stub(self):
        assert wa.build_citations(SAMPLE_CONTEXTS)[0].origin == "stub"

    def test_respects_provided_origin(self):
        cites = wa.build_citations([{"source_id": "n1", "text": "x", "origin": "news"}])
        assert cites[0].origin == "news"


class TestFallbackDraft:
    def test_is_nonempty_and_deterministic(self):
        d1 = wa.fallback_draft("台積電營收", SAMPLE_CONTEXTS)
        d2 = wa.fallback_draft("台積電營收", SAMPLE_CONTEXTS)
        assert d1 and d1 == d2

    def test_references_a_source_id(self):
        draft = wa.fallback_draft("台積電營收", SAMPLE_CONTEXTS)
        assert "doc-1" in draft

    def test_contains_no_buysell_keywords(self):
        from polaris.graph.compliance import BUYSELL_KEYWORDS

        draft = wa.fallback_draft("台積電營收", SAMPLE_CONTEXTS)
        assert all(kw not in draft for kw in BUYSELL_KEYWORDS)


class TestLLMDraft:
    def test_uses_pro_model_and_passes_contexts(self):
        from tests.conftest import FakeLLM

        client = FakeLLM("依據 doc-1，營收成長。")
        draft = wa.llm_draft("台積電營收", SAMPLE_CONTEXTS, client)

        assert draft == "依據 doc-1，營收成長。"
        assert client.calls[0]["flash"] is False  # 撰寫用 Pro
        assert client.calls[0]["system_instruction"]
        assert "台積電營收" in client.calls[0]["prompt"]
        assert "台積電 2025Q1 營收 8,000 億元。" in client.calls[0]["prompt"]


class TestMakeDraft:
    def test_no_client_uses_fallback(self):
        draft, cites = wa.make_draft("台積電營收", SAMPLE_CONTEXTS, None)
        assert draft == wa.fallback_draft("台積電營收", SAMPLE_CONTEXTS)
        assert len(cites) == 2

    def test_with_client_uses_llm_draft(self):
        from tests.conftest import FakeLLM

        draft, cites = wa.make_draft("q", SAMPLE_CONTEXTS, FakeLLM("LLM 草稿"))
        assert draft == "LLM 草稿"
        assert len(cites) == 2

    def test_empty_llm_output_falls_back(self):
        from tests.conftest import FakeLLM

        draft, _ = wa.make_draft("q", SAMPLE_CONTEXTS, FakeLLM("  "))
        assert draft == wa.fallback_draft("q", SAMPLE_CONTEXTS)


class TestWriterNodeIntegration:
    def test_workflow_uses_llm_draft_when_client_available(self, monkeypatch):
        from tests.conftest import FakeLLM
        from polaris.graph.nodes import stubs

        # planner 與 writer 都會呼叫 active_llm()；回同一 FakeLLM 即可
        monkeypatch.setattr(stubs, "active_llm", lambda: FakeLLM("根據引用，營收上升。"))

        from polaris.graph.workflow import build_workflow

        result = build_workflow().invoke({"query": "台積電 Q1"})
        assert result.get("answer") == "根據引用，營收上升。"
        assert result.get("compliance_status") == "passed"
        assert len(result.get("citations") or []) >= 1

    def test_llm_buysell_draft_still_blocked_by_compliance(self, monkeypatch):
        """NFR-031：LLM 即使越線產生買賣建議，最終輸出仍被攔成安全訊息。"""
        from tests.conftest import FakeLLM
        from polaris.graph.compliance import BUYSELL_KEYWORDS, SAFE_MESSAGE
        from polaris.graph.nodes import stubs

        monkeypatch.setattr(stubs, "active_llm", lambda: FakeLLM("我建議買進台積電。"))

        from polaris.graph.workflow import build_workflow

        result = build_workflow().invoke({"query": "該買台積電嗎"})
        ans = result.get("answer", "")
        assert result.get("compliance_status") == "blocked"
        assert ans == SAFE_MESSAGE
        assert all(kw not in ans for kw in BUYSELL_KEYWORDS)
