"""D9 — Compliance Agent：6 關鍵字確定性 floor + Gemini smart 層（fail-to-floor）。

- Layer 1 floor 永遠先跑、命中即收、LLM 永不解除。
- Layer 2 LLM 只「加攔」隱性建議，且永不改寫 draft（攔截恆回 SAFE_MESSAGE）。
- fail-to-floor：LLM 任何失敗都退回 floor 結果，絕不弱化既有保證。
- 無金鑰（CI）→ floor-only → 與今天行為一致。
"""
from __future__ import annotations

from polaris.graph.compliance import SAFE_MESSAGE
from polaris.graph.nodes import compliance_agent as ca

KEYWORD_DRAFT = "分析師看多台積電，理由為產能釋出。"  # 含關鍵字「看多」
ADVISORY_DRAFT = "台積電基本面強勁，這檔現在很適合進場布局。"  # 零關鍵字但隱性建議
CLEAN_DRAFT = "台積電 2025 Q1 營收 YoY 約 12.34%，毛利率約 58%。"


class TestReviewFloor:
    def test_keyword_blocked_without_client(self):
        final, status = ca.review(KEYWORD_DRAFT, None)
        assert status == "blocked"
        assert final == SAFE_MESSAGE

    def test_keyword_block_does_not_consult_llm(self):
        from tests.conftest import FakeLLM

        client = FakeLLM("CLEAN")  # 即使 LLM 會說 clean，floor 命中也不諮詢、不解除
        final, status = ca.review(KEYWORD_DRAFT, client)
        assert status == "blocked"
        assert final == SAFE_MESSAGE
        assert client.calls == []  # floor 短路 → LLM 完全不被呼叫

    def test_clean_draft_passed_without_client(self):
        final, status = ca.review(CLEAN_DRAFT, None)
        assert status == "passed"
        assert final == CLEAN_DRAFT


class TestLLMLayer:
    def test_advisory_flagged_blocks(self):
        from tests.conftest import FakeLLM

        final, status = ca.review(ADVISORY_DRAFT, FakeLLM("VIOLATION"))
        assert status == "blocked"
        assert final == SAFE_MESSAGE

    def test_clean_verdict_passes_unchanged(self):
        from tests.conftest import FakeLLM

        final, status = ca.review(ADVISORY_DRAFT, FakeLLM("CLEAN"))
        assert status == "passed"
        assert final == ADVISORY_DRAFT  # LLM 不改寫

    def test_verdict_call_uses_flash_and_system_instruction(self):
        from tests.conftest import FakeLLM

        client = FakeLLM("CLEAN")
        ca.llm_flags_violation(ADVISORY_DRAFT, client)
        assert client.calls[0]["flash"] is True  # 分類用 Flash
        assert client.calls[0]["system_instruction"]
        assert ADVISORY_DRAFT in client.calls[0]["prompt"]


class TestVerdictParsing:
    def test_violation_token_true(self):
        from tests.conftest import FakeLLM

        assert ca.llm_flags_violation("x", FakeLLM("VIOLATION")) is True

    def test_chinese_violation_true(self):
        from tests.conftest import FakeLLM

        assert ca.llm_flags_violation("x", FakeLLM("違規：屬投資建議")) is True

    def test_clean_token_false(self):
        from tests.conftest import FakeLLM

        assert ca.llm_flags_violation("x", FakeLLM("CLEAN")) is False

    def test_empty_verdict_false(self):
        from tests.conftest import FakeLLM

        assert ca.llm_flags_violation("x", FakeLLM("   ")) is False


class TestFailToFloor:
    def test_persistent_transient_defers_to_floor(self, no_retry_sleep):
        from tests.conftest import ApiError, FakeLLM

        client = FakeLLM("VIOLATION", fail_times=99, error=ApiError(503))
        final, status = ca.review(ADVISORY_DRAFT, client)
        assert status == "passed"  # LLM 持續錯 → 退 floor（draft 無關鍵字 → passed）
        assert final == ADVISORY_DRAFT
        assert len(client.calls) == 3  # D7 retry 3 次用盡

    def test_permanent_error_not_retried_defers_to_floor(self):
        from tests.conftest import ApiError, FakeLLM

        client = FakeLLM("VIOLATION", fail_times=99, error=ApiError(400))
        final, status = ca.review(ADVISORY_DRAFT, client)
        assert status == "passed"
        assert len(client.calls) == 1  # 永久性 → 不重試

    def test_floor_still_guards_when_llm_would_error(self, no_retry_sleep):
        """LLM 掛掉也不能放行含關鍵字的 draft（floor 先跑、與 LLM 無關）。"""
        from tests.conftest import ApiError, FakeLLM

        client = FakeLLM("CLEAN", fail_times=99, error=ApiError(503))
        final, status = ca.review(KEYWORD_DRAFT, client)
        assert status == "blocked"
        assert client.calls == []  # floor 命中 → 根本不呼叫 LLM


class TestComplianceNodeIntegration:
    def test_node_blocks_advisory_when_llm_flags(self, monkeypatch):
        from tests.conftest import FakeLLM
        from polaris.graph.nodes import stubs

        monkeypatch.setattr(stubs, "active_llm", lambda: FakeLLM("VIOLATION"))
        patch = stubs.compliance({"draft": ADVISORY_DRAFT})
        assert patch["compliance_status"] == "blocked"
        assert patch["answer"] == SAFE_MESSAGE

    def test_node_passes_clean_when_no_key(self, monkeypatch):
        from polaris.graph.nodes import stubs

        monkeypatch.setattr(stubs, "active_llm", lambda: None)
        patch = stubs.compliance({"draft": CLEAN_DRAFT})
        assert patch["compliance_status"] == "passed"
        assert patch["answer"] == CLEAN_DRAFT
