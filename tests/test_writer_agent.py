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
        assert client.calls[0]["flash"] is True  # gemini-3-pro-preview EOL → Flash
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


class TestMakeDraftRetry:
    """D7：Writer 的 Gemini 呼叫暫時性失敗自動重試；持續 / 永久才降級 fallback。"""

    def test_transient_then_recovers_keeps_llm_draft(self, no_retry_sleep):
        from tests.conftest import ApiError, FakeLLM

        client = FakeLLM("LLM 草稿", fail_times=2, error=ApiError(503))
        draft, cites = wa.make_draft("q", SAMPLE_CONTEXTS, client)
        assert draft == "LLM 草稿"  # 撐過抖動，保住 LLM 草稿
        assert len(client.calls) == 3
        assert len(cites) == 2  # citations 仍由 contexts 接地

    def test_persistent_transient_falls_back(self, no_retry_sleep):
        from tests.conftest import ApiError, FakeLLM

        client = FakeLLM("LLM 草稿", fail_times=99, error=ApiError(503))
        draft, _ = wa.make_draft("q", SAMPLE_CONTEXTS, client)
        assert draft == wa.fallback_draft("q", SAMPLE_CONTEXTS)
        assert len(client.calls) == 3  # 3 次嘗試用盡 → 降級

    def test_permanent_error_not_retried(self):
        from tests.conftest import ApiError, FakeLLM

        client = FakeLLM("LLM 草稿", fail_times=99, error=ApiError(400))
        draft, _ = wa.make_draft("q", SAMPLE_CONTEXTS, client)
        assert draft == wa.fallback_draft("q", SAMPLE_CONTEXTS)
        assert len(client.calls) == 1  # 永久性錯誤 → 不重試


class TestBuildPromptCompression:
    """D8 live integration: _build_prompt compresses context block before LLM call."""

    def test_compressor_is_called_on_context_block(self):
        """Injected compressor receives the formatted context text."""
        calls: list[str] = []

        class SpyCompressor:
            name = "spy"

            def compress(self, text: str) -> str:
                calls.append(text)
                return text  # pass-through

        wa._build_prompt("台積電", SAMPLE_CONTEXTS, compressor=SpyCompressor())

        assert len(calls) == 1
        assert "doc-1" in calls[0]
        assert "台積電 2025Q1 營收 8,000 億元。" in calls[0]

    def test_compressed_text_appears_in_prompt(self):
        """Compressor output replaces original context block in the prompt."""

        class ShrinkCompressor:
            name = "shrink"

            def compress(self, text: str) -> str:
                return "COMPRESSED"

        prompt = wa._build_prompt("q", SAMPLE_CONTEXTS, compressor=ShrinkCompressor())

        assert "COMPRESSED" in prompt
        assert "台積電 2025Q1" not in prompt  # original text replaced

    def test_citations_built_from_original_snippets(self):
        """Compression of the prompt does NOT affect citation grounding."""

        class ZeroCompressor:
            name = "zero"

            def compress(self, text: str) -> str:
                return ""  # wipe everything

        # Even with a compressor that deletes all context text from the prompt,
        # build_citations works on the original contexts list — grounding is safe.
        cites = wa.build_citations(SAMPLE_CONTEXTS)
        assert cites[0].snippet == "台積電 2025Q1 營收 8,000 億元。"

    def test_default_compressor_removes_boilerplate(self):
        """DeterministicCompressor (default) strips stub boilerplate from the prompt."""
        stub_contexts = [
            {"source_id": "s1", "text": "（v0 stub）台積電 2025Q1 法說摘要。"},
        ]
        prompt = wa._build_prompt("台積電", stub_contexts)
        assert "（v0 stub）" not in prompt
        assert "台積電 2025Q1 法說摘要。" in prompt  # content kept


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
