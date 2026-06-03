"""D13 — Deep Research ReAct prompt 機制（polaris.graph.deep_research.react）。

prompt + 工具協定 + action parser 是 D15 loop 的 contract。parser 對格式錯誤
須安全退 finish（loop 永遠能優雅終止）。
"""
from __future__ import annotations

from polaris.graph.deep_research import react


class TestRenderTools:
    def test_lists_tool_names(self):
        out = react.render_tools(react.DEFAULT_TOOLS)
        assert "search" in out and "finish" in out


class TestBuildReactPrompt:
    def test_includes_question_and_tools(self):
        out = react.build_react_prompt("台積電 2025Q1 毛利率")
        assert "台積電 2025Q1 毛利率" in out
        assert "search" in out

    def test_includes_scratchpad_of_prior_steps(self):
        steps = [
            {"thought": "t1", "action": "search", "action_input": "q1", "observation": "o1"}
        ]
        out = react.build_react_prompt("Q", steps)
        assert "q1" in out and "o1" in out

    def test_no_scratchpad_when_no_steps(self):
        out = react.build_react_prompt("Q", [])
        assert "Q" in out  # 不崩、含問題


class TestParseReactAction:
    def test_parses_search_action_and_input(self):
        a = react.parse_react_action(
            "Thought: 找資料\nAction: search\nAction Input: 台積電 毛利率"
        )
        assert a.tool == "search"
        assert a.tool_input == "台積電 毛利率"
        assert a.is_finish is False

    def test_parses_finish(self):
        a = react.parse_react_action("Thought: 夠了\nAction: finish\nAction Input: 最終結論…")
        assert a.is_finish is True
        assert a.tool == "finish"
        assert "結論" in a.tool_input

    def test_malformed_defaults_to_finish(self):
        a = react.parse_react_action("胡言亂語、沒有任何格式")
        assert a.is_finish is True

    def test_empty_defaults_to_finish(self):
        assert react.parse_react_action("").is_finish is True

    def test_case_insensitive_and_whitespace(self):
        a = react.parse_react_action("action:  SEARCH \naction input:  q  ")
        assert a.tool == "search"
        assert a.tool_input == "q"
