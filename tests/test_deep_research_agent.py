"""D15 — Deep Research v0 ReAct loop（polaris.graph.deep_research.agent）。

純 Python bounded loop：smart(LLM)/確定性 fallback 雙路徑、≤6 迴圈、evidence 累積、
最終結論過 D9 Compliance（NFR-031）。全程無金鑰可跑（stub_search + 確定性政策）。
"""
from __future__ import annotations

from polaris.graph.deep_research import agent as ag
from polaris.graph.deep_research.state import DeepResearchResult
from polaris.graph.state import Citation


class _ScriptedLLM:
    """每次 generate 回 responses 下一則；用盡回 default（避免 compliance 取用時爆）。"""

    def __init__(self, responses, default="CLEAN"):
        self._responses = list(responses)
        self._default = default
        self.calls = []

    def generate(self, prompt, *, flash=False, system_instruction=None):
        self.calls.append({"prompt": prompt, "flash": flash})
        return self._responses.pop(0) if self._responses else self._default


class _BoomLLM:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, flash=False, system_instruction=None):
        self.calls.append(prompt)
        raise RuntimeError("boom")  # 非暫時性 → call_with_retry 立即 re-raise（不 sleep）


class TestStubSearch:
    def test_returns_citations(self):
        out = ag.stub_search("台積電 營收")
        assert out and all(isinstance(c, Citation) for c in out)

    def test_deterministic(self):
        assert [c.source_id for c in ag.stub_search("x")] == [
            c.source_id for c in ag.stub_search("x")
        ]

    def test_distinct_per_query(self):
        assert ag.stub_search("台積電 營收")[0].source_id != ag.stub_search("台積電 毛利率")[0].source_id


class TestDeterministicRun:
    def test_runs_to_answered_with_evidence(self):
        r = ag.run_deep_research("台積電 2025Q1 體質")
        assert isinstance(r, DeepResearchResult)
        assert r.status == "answered"
        assert len(r.evidence) >= 3
        assert 1 <= r.iterations <= 6
        assert r.final_answer.strip()
        assert r.compliance_status == "passed"
        assert any(s.action == "search" for s in r.react_steps)
        assert any(s.action == "finish" for s in r.react_steps)

    def test_deterministic_repeatable(self):
        r1 = ag.run_deep_research("台積電 Q1")
        r2 = ag.run_deep_research("台積電 Q1")
        assert r1.final_answer == r2.final_answer
        assert [c.source_id for c in r1.evidence] == [c.source_id for c in r2.evidence]
        assert r1.iterations == r2.iterations

    def test_no_buysell_in_answer(self):
        from polaris.graph.compliance import BUYSELL_KEYWORDS

        r = ag.run_deep_research("該買台積電嗎")
        assert all(kw not in r.final_answer for kw in BUYSELL_KEYWORDS)


class TestBounded:
    def test_exhausts_at_max_loops_when_no_evidence(self):
        r = ag.run_deep_research("Q", search=lambda q: [], max_loops=3)
        assert r.iterations == 3
        assert r.status == "exhausted"
        assert r.final_answer.strip()  # 不崩、誠實結論


class TestSmartPath:
    def test_llm_finish_single_iteration(self):
        client = _ScriptedLLM(["Thought: 夠了\nAction: finish\nAction Input: 根據引用，營收成長。"])
        r = ag.run_deep_research("台積電 Q1", client=client)
        assert r.status == "answered"
        assert r.final_answer == "根據引用，營收成長。"
        assert r.iterations == 1
        assert r.compliance_status == "passed"

    def test_llm_search_then_finish(self):
        client = _ScriptedLLM(
            [
                "Thought: 找\nAction: search\nAction Input: 台積電 營收",
                "Thought: 再找\nAction: search\nAction Input: 台積電 毛利率",
                "Thought: 夠了\nAction: finish\nAction Input: 綜合結論。",
            ]
        )
        r = ag.run_deep_research("台積電 Q1", client=client)
        assert r.status == "answered"
        assert r.iterations == 3
        assert len(r.evidence) == 2
        assert [s.action for s in r.react_steps] == ["search", "search", "finish"]

    def test_llm_failure_degrades_to_deterministic(self, no_retry_sleep):
        r = ag.run_deep_research("台積電 Q1", client=_BoomLLM())
        assert r.status == "answered"  # 退確定性仍完成
        assert len(r.evidence) >= 3


class TestCompliance:
    def test_advisory_finish_blocked(self):
        from polaris.graph.compliance import SAFE_MESSAGE

        client = _ScriptedLLM(["Thought:\nAction: finish\nAction Input: 我建議買進台積電。"])
        r = ag.run_deep_research("台積電", client=client)
        assert r.compliance_status == "blocked"
        assert r.final_answer == SAFE_MESSAGE


class TestSearchSeam:
    def test_injected_search_used(self):
        calls = []

        def fake_search(q):
            calls.append(q)
            return [Citation(source_id=f"x-{len(calls)}", snippet="片段", origin="stub")]

        r = ag.run_deep_research("Q", search=fake_search)
        assert calls  # 注入的 search 被呼叫
        assert r.status == "answered"
