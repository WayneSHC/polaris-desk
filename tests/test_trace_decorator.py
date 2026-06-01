"""T005 — 測試 src/polaris/graph/nodes/trace.py 的 @traced 裝飾器。

@traced(node_name) 包住節點函式，行為契約：

- 正常路徑：回 ``{**fn_patch, "trace": [NodeTrace(status='ok', ...)]}``
- 例外路徑：吞掉例外，回 ``{"trace": [NodeTrace(status='error', error_message=str(e))], "halt": True}``，
  不讓下游節點吃到 undefined 狀態（FR-009）。
- input_keys 取自包進來的 state.keys()，output_keys 取自節點回的 patch keys。
- 兩次呼叫各回一筆 trace，外層用 operator.add reducer 即可累加（FR-006 / SC-002）。

注意：裝飾器本身不直接累加 trace（這是 LangGraph reducer 的職責）；
只負責產出單筆 trace 的「patch shape」。
"""
from __future__ import annotations

import operator
import time


def _import_traced():
    from polaris.graph.nodes.trace import traced
    return traced


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestTracedHappyPath:

    def test_returns_node_patch_plus_single_trace(self):
        traced = _import_traced()

        @traced("planner")
        def node(state):
            return {"plan": ["a", "b"]}

        patch = node({"query": "hi"})

        assert patch.get("plan") == ["a", "b"]
        assert "trace" in patch
        assert len(patch["trace"]) == 1
        assert patch["trace"][0].node_name == "planner"
        assert patch["trace"][0].status == "ok"

    def test_captures_input_and_output_keys_sorted(self):
        traced = _import_traced()

        @traced("retriever")
        def node(state):
            return {"contexts": [{"id": 1}], "extra": "ignored"}

        patch = node({"query": "hi", "plan": ["a"]})

        t = patch["trace"][0]
        assert t.input_keys == ["plan", "query"]
        assert t.output_keys == ["contexts", "extra"]
        assert t.error_message is None

    def test_node_returning_none_treated_as_empty_patch(self):
        """節點函式回 None（沒 state patch）也要 work — 仍記一筆 ok trace。"""
        traced = _import_traced()

        @traced("noop")
        def node(state):
            return None

        patch = node({"query": "hi"})
        assert patch.get("trace") and patch["trace"][0].status == "ok"
        assert patch["trace"][0].output_keys == []

    def test_elapsed_ms_non_negative(self):
        traced = _import_traced()

        @traced("slow")
        def node(state):
            time.sleep(0.001)
            return {}

        patch = node({"query": "hi"})
        assert patch["trace"][0].elapsed_ms >= 0  # 不可為負（pydantic 已強制，這裡再驗）

    def test_does_not_mutate_input_state(self):
        """裝飾器不應改原 state dict（避免共享狀態 bug）。"""
        traced = _import_traced()

        @traced("planner")
        def node(state):
            return {"plan": ["x"]}

        original = {"query": "hi"}
        snapshot = dict(original)
        _ = node(original)
        assert original == snapshot


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------

class TestTracedErrorPath:

    def test_swallows_exception_and_emits_error_trace(self):
        traced = _import_traced()

        @traced("retriever")
        def node(state):
            raise RuntimeError("boom")

        # 不應 propagate；裝飾器吞掉
        patch = node({"query": "hi"})

        assert patch.get("halt") is True
        assert len(patch["trace"]) == 1
        t = patch["trace"][0]
        assert t.node_name == "retriever"
        assert t.status == "error"
        assert t.error_message is not None
        assert "boom" in t.error_message

    def test_error_trace_records_input_keys_but_empty_output(self):
        traced = _import_traced()

        @traced("retriever")
        def node(state):
            raise ValueError("bad")

        patch = node({"query": "hi", "plan": ["a"]})

        t = patch["trace"][0]
        assert t.input_keys == ["plan", "query"]
        assert t.output_keys == []

    def test_error_path_does_not_include_node_patch(self):
        """節點掛掉 → 不可有節點 patch（避免半成品 state）。"""
        traced = _import_traced()

        @traced("calc")
        def node(state):
            partial = {"calculations": {"x": 1}}
            raise RuntimeError("after partial")
            return partial  # noqa: unreachable - 編譯器知道，但行為示意

        patch = node({"query": "hi"})

        # halt + trace 必須有，但 calculations 不可漏出
        assert patch.get("halt") is True
        assert "calculations" not in patch


# ---------------------------------------------------------------------------
# Reducer compatibility — 兩次呼叫的 trace 用 operator.add 可串接
# ---------------------------------------------------------------------------

class TestTracedReducerShape:
    """裝飾器產出的 trace 一律 list，外層用 ``operator.add`` 累加。"""

    def test_two_calls_accumulate_via_operator_add(self):
        traced = _import_traced()

        @traced("planner")
        def planner(state):
            return {"plan": ["a"]}

        @traced("writer")
        def writer(state):
            return {"draft": "x"}

        p1 = planner({"query": "hi"})
        p2 = writer({"query": "hi", "plan": ["a"]})
        merged = operator.add(p1["trace"], p2["trace"])

        assert len(merged) == 2
        assert merged[0].node_name == "planner"
        assert merged[1].node_name == "writer"

    def test_same_node_called_twice_accumulates(self):
        """同一節點被呼叫兩次（如未來 retry），各記一筆。"""
        traced = _import_traced()

        @traced("planner")
        def planner(state):
            return {"plan": ["a"]}

        p1 = planner({"query": "hi"})
        p2 = planner({"query": "hi"})
        merged = operator.add(p1["trace"], p2["trace"])

        assert len(merged) == 2
        assert all(t.node_name == "planner" for t in merged)
