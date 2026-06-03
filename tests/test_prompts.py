"""D13 — 中央 prompt registry（polaris.graph.prompts）。

共用片段（NO_ADVICE_CLAUSE / GROUNDING_CLAUSE）是 single source of truth；
生成型 prompt（planner/writer/react）都須含 NO_ADVICE_CLAUSE（NFR-031 跨 prompt
不變量）。既有模組的 prompt 常數須仍可 import（backward-compat）。
"""
from __future__ import annotations

import pytest

from polaris.graph import prompts as p


class TestSharedFragments:
    def test_no_advice_clause_nonempty(self):
        assert p.NO_ADVICE_CLAUSE.strip()

    def test_grounding_clause_nonempty(self):
        assert p.GROUNDING_CLAUSE.strip()


class TestSystemPrompts:
    @pytest.mark.parametrize(
        "name",
        [
            "PLANNER_SYSTEM_PROMPT",
            "WRITER_SYSTEM_PROMPT",
            "COMPLIANCE_SYSTEM_PROMPT",
            "REACT_SYSTEM_PROMPT",
        ],
    )
    def test_prompt_nonempty(self, name):
        assert getattr(p, name).strip()

    @pytest.mark.parametrize(
        "name", ["PLANNER_SYSTEM_PROMPT", "WRITER_SYSTEM_PROMPT", "REACT_SYSTEM_PROMPT"]
    )
    def test_generator_prompts_forbid_advice(self, name):
        # NFR-031 跨生成型 prompt 不變量：皆含單一 NO_ADVICE_CLAUSE
        assert p.NO_ADVICE_CLAUSE in getattr(p, name)

    @pytest.mark.parametrize("name", ["WRITER_SYSTEM_PROMPT", "REACT_SYSTEM_PROMPT"])
    def test_grounding_in_writer_and_react(self, name):
        assert p.GROUNDING_CLAUSE in getattr(p, name)

    def test_react_prompt_states_loop_and_citation_goals(self):
        # ≤6 迴圈 / ≥3 引用 意識（FR-004）
        assert "6" in p.REACT_SYSTEM_PROMPT
        assert "3" in p.REACT_SYSTEM_PROMPT


class TestBackwardCompat:
    def test_planner_reexports_system_prompt(self):
        from polaris.graph.nodes import planner_agent as pa

        assert pa.SYSTEM_PROMPT.strip()

    def test_writer_reexports_system_prompt(self):
        from polaris.graph.nodes import writer_agent as wa

        assert wa.SYSTEM_PROMPT.strip()

    def test_compliance_reexports_system_prompt(self):
        from polaris.graph.nodes import compliance_agent as ca

        assert ca.COMPLIANCE_SYSTEM_PROMPT.strip()
