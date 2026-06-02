"""D2 — Planner Agent v0：query → plan: list[str]（2–5 步）。

兩條路徑都要確定性可測：
- LLM 路徑：注入 FakeLLM，解析其輸出成步驟清單。
- fallback 路徑：無 client（無金鑰）時走啟發式拆解，確定性。
"""
from __future__ import annotations

from polaris.graph.nodes import planner_agent as pa


class TestFallbackPlan:
    def test_returns_between_2_and_5_nonempty_steps(self):
        steps = pa.fallback_plan("台積電 2025 Q1 營收 YoY 是多少？")
        assert 2 <= len(steps) <= 5
        assert all(isinstance(s, str) and s.strip() for s in steps)

    def test_is_deterministic(self):
        q = "聯發科最近兩季毛利率趨勢"
        assert pa.fallback_plan(q) == pa.fallback_plan(q)

    def test_last_step_mentions_citation_grounding(self):
        # 接地是憲法核心：計畫最後一步應指向「標引用 / 來源」
        steps = pa.fallback_plan("台積電營收")
        assert any(("引用" in s) or ("來源" in s) for s in steps)


class TestParsePlan:
    def test_parses_numbered_list(self):
        text = "1. 擷取相關段落\n2. 計算指標\n3. 撰寫並標引用"
        assert pa.parse_plan(text) == ["擷取相關段落", "計算指標", "撰寫並標引用"]

    def test_drops_preamble_when_markers_present(self):
        text = "以下是步驟：\n- 找資料\n- 算數字"
        assert pa.parse_plan(text) == ["找資料", "算數字"]

    def test_falls_back_to_nonempty_lines_without_markers(self):
        text = "找資料\n算數字"
        assert pa.parse_plan(text) == ["找資料", "算數字"]

    def test_ignores_blank_lines(self):
        text = "\n1. 只有一步\n   \n"
        assert pa.parse_plan(text) == ["只有一步"]


class TestLLMPlan:
    def test_uses_flash_and_system_instruction(self):
        from tests.conftest import FakeLLM

        client = FakeLLM("1. A\n2. B")
        steps = pa.llm_plan("台積電 Q1 營收", client)

        assert steps == ["A", "B"]
        assert len(client.calls) == 1
        assert client.calls[0]["flash"] is True
        assert client.calls[0]["system_instruction"]  # 非空
        assert "台積電 Q1 營收" in client.calls[0]["prompt"]


class TestMakePlan:
    def test_no_client_uses_fallback(self):
        q = "台積電營收"
        assert pa.make_plan(q, None) == pa.fallback_plan(q)

    def test_with_client_uses_llm_output(self):
        from tests.conftest import FakeLLM

        steps = pa.make_plan("台積電營收", FakeLLM("1. X\n2. Y\n3. Z"))
        assert steps == ["X", "Y", "Z"]

    def test_empty_llm_output_falls_back(self):
        from tests.conftest import FakeLLM

        q = "台積電營收"
        assert pa.make_plan(q, FakeLLM("   ")) == pa.fallback_plan(q)

    def test_llm_exception_falls_back(self):
        class BoomLLM:
            def generate(self, *a, **k):
                raise RuntimeError("boom")

        q = "台積電營收"
        assert pa.make_plan(q, BoomLLM()) == pa.fallback_plan(q)


class TestPlannerNodeIntegration:
    """節點接進 workflow 後：有金鑰走 LLM、無金鑰走 fallback（皆確定性）。"""

    def test_workflow_uses_llm_plan_when_client_available(self, monkeypatch):
        from tests.conftest import FakeLLM
        from polaris.graph.nodes import stubs

        monkeypatch.setattr(stubs, "active_llm", lambda: FakeLLM("1. 步驟甲\n2. 步驟乙"))

        from polaris.graph.workflow import build_workflow

        result = build_workflow().invoke({"query": "台積電 Q1"})
        assert result.get("plan") == ["步驟甲", "步驟乙"]

    def test_workflow_uses_fallback_when_no_client(self, monkeypatch):
        from polaris.graph.nodes import stubs

        monkeypatch.setattr(stubs, "active_llm", lambda: None)

        from polaris.graph.workflow import build_workflow

        result = build_workflow().invoke({"query": "台積電 Q1"})
        assert result.get("plan") == pa.fallback_plan("台積電 Q1")
