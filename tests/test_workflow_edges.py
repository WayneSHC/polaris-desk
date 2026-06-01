"""US1 — Workflow edge cases: empty query + node exception (T009/T010).

對應 spec FR-008 / FR-009 / SC-007。

注意：spec SC-007 與 tasks.md T010 對「halt 後下游節點是否出現在 trace」描述不一致。
本測試以 **spec 為準**（憲法層級高於 tasks.md）：
- halt 後下游節點**不出現**在 trace（直接跳 terminal）。
- T010 改為斷言「retriever 例外 → trace 只含 planner + retriever，無 skipped 條目」。
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# T009 — empty query halt（FR-008 / SC-007）
# ---------------------------------------------------------------------------

class TestEmptyQuery:

    def _invoke_with(self, query: str):
        from polaris.graph.workflow import build_workflow
        app = build_workflow()
        return app.invoke({"query": query})

    def test_empty_string_halts(self):
        result = self._invoke_with("")
        assert result.get("halt") is True
        assert result.get("answer") == "請提供具體問題。"

    def test_whitespace_only_halts(self):
        result = self._invoke_with("   \t \n  ")
        assert result.get("halt") is True
        assert result.get("answer") == "請提供具體問題。"

    def test_only_planner_in_trace(self):
        """SC-007：「下游 4 節點 status 不存在」— trace 只有 1 筆 planner。"""
        result = self._invoke_with("")
        trace = result.get("trace") or []
        assert len(trace) == 1
        assert trace[0].node_name == "planner"
        assert trace[0].status == "error"

    def test_compliance_status_unknown_on_halt(self):
        result = self._invoke_with("")
        assert result.get("compliance_status") == "unknown"


# ---------------------------------------------------------------------------
# T010 — node exception halts downstream（FR-009）
# ---------------------------------------------------------------------------

class TestNodeException:

    def test_retriever_exception_does_not_propagate(self, monkeypatch):
        """app.invoke 不可拋例外 — @traced 應吞掉並設 halt。"""
        from polaris.graph.nodes import stubs
        from polaris.graph.nodes.trace import traced

        @traced("retriever")
        def failing_retriever(state):
            raise RuntimeError("boom")

        monkeypatch.setattr(stubs, "retriever", failing_retriever)

        from polaris.graph.workflow import build_workflow
        app = build_workflow()
        # 不應 raise
        result = app.invoke({"query": "test"})
        assert result.get("halt") is True

    def test_retriever_exception_trace_shape(self, monkeypatch):
        """trace 含 planner ok + retriever error，下游不出現（依 SC-007 spirit）。"""
        from polaris.graph.nodes import stubs
        from polaris.graph.nodes.trace import traced

        @traced("retriever")
        def failing_retriever(state):
            raise RuntimeError("boom from retriever")

        monkeypatch.setattr(stubs, "retriever", failing_retriever)

        from polaris.graph.workflow import build_workflow
        app = build_workflow()
        result = app.invoke({"query": "test"})

        trace = result.get("trace") or []
        names = [t.node_name for t in trace]
        assert names == ["planner", "retriever"]
        assert trace[0].status == "ok"
        assert trace[1].status == "error"
        assert "boom from retriever" in (trace[1].error_message or "")

    def test_retriever_exception_terminal_answer_mentions_node(self, monkeypatch):
        """terminal 訊息應點名出錯的節點，便於 debug。"""
        from polaris.graph.nodes import stubs
        from polaris.graph.nodes.trace import traced

        @traced("retriever")
        def failing_retriever(state):
            raise RuntimeError("boom")

        monkeypatch.setattr(stubs, "retriever", failing_retriever)

        from polaris.graph.workflow import build_workflow
        app = build_workflow()
        result = app.invoke({"query": "test"})

        ans = result.get("answer", "")
        assert "錯誤" in ans
        assert "retriever" in ans
