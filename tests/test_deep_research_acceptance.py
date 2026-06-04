"""D16 — Deep Research v1 過驗收（場景 2：同業比較）。

驗收門檻（FR-004）：≤6 迴圈 / ≥3 引用 / 句句可溯源 / 0 買賣建議。
另測 `is_fully_traceable` 與 v1 硬保證（未可溯源 + 有 evidence → 轉結構化 grounded）。
"""
from __future__ import annotations

from polaris.graph.compliance import BUYSELL_KEYWORDS
from polaris.graph.deep_research import agent as ag
from polaris.graph.deep_research.state import is_fully_traceable
from polaris.graph.state import Citation

SCENARIO_2_Q = "比較台積電與聯發科最近兩季的毛利率變化"


def _c(sid: str, snip: str = "片段") -> Citation:
    return Citation(source_id=sid, snippet=snip, origin="stub")


class _ScriptedLLM:
    def __init__(self, responses, default="CLEAN"):
        self._r = list(responses)
        self._default = default
        self.calls = []

    def generate(self, prompt, *, flash=False, system_instruction=None):
        self.calls.append(prompt)
        return self._r.pop(0) if self._r else self._default


class TestIsFullyTraceable:
    def test_all_valid_tags_true(self):
        ev = [_c("a"), _c("b")]
        ans = "摘要：\n- 甲（來源：a）\n- 乙（來源：b）\n結語。"
        assert is_fully_traceable(ans, ev) is True

    def test_bullet_missing_tag_false(self):
        ev = [_c("a")]
        ans = "摘要：\n- 甲（來源：a）\n- 乙\n"
        assert is_fully_traceable(ans, ev) is False

    def test_tag_not_in_evidence_false(self):
        ans = "- 甲（來源：zzz）"
        assert is_fully_traceable(ans, [_c("a")]) is False

    def test_free_text_false(self):
        assert is_fully_traceable("一段沒有條列也沒有來源的自由文。", [_c("a")]) is False

    def test_no_bullets_false(self):
        assert is_fully_traceable("摘要：\n本回答不提供買賣建議。", [_c("a")]) is False


class TestAcceptanceScenario2:
    def test_passes_all_four_criteria(self):
        r = ag.run_deep_research(SCENARIO_2_Q)
        assert r.iterations <= 6  # ≤6 迴圈
        assert len(r.evidence) >= 3  # ≥3 引用
        assert is_fully_traceable(r.final_answer, r.evidence)  # 句句可溯源
        assert r.compliance_status == "passed"  # 過合規
        assert all(kw not in r.final_answer for kw in BUYSELL_KEYWORDS)  # 0 買賣建議

    def test_repeatable(self):
        r1 = ag.run_deep_research(SCENARIO_2_Q)
        r2 = ag.run_deep_research(SCENARIO_2_Q)
        assert r1.final_answer == r2.final_answer
        assert r1.iterations == r2.iterations


class TestTraceabilityGuarantee:
    def test_llm_freetext_with_evidence_becomes_traceable(self):
        client = _ScriptedLLM(
            [
                "Thought:\nAction: search\nAction Input: 台積電 毛利率",
                "Thought:\nAction: search\nAction Input: 聯發科 毛利率",
                "Thought:\nAction: search\nAction Input: 兩家近兩季比較",
                "Thought:\nAction: finish\nAction Input: 一段沒有來源標註的自由文結論。",
            ]
        )
        r = ag.run_deep_research(SCENARIO_2_Q, client=client)
        assert len(r.evidence) >= 3
        # LLM 自由文未可溯源 + 有 evidence → 硬保證轉結構化 grounded
        assert is_fully_traceable(r.final_answer, r.evidence)
