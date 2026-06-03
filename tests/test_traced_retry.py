"""D7 Tier 2 — @traced 節點層保險絲：暫時性失敗在節點內自動重試。

重點：retry 發生在 @traced 既有的例外邊界**內**，用盡後例外照樣變成
error trace + halt=True（FR-009 不變：不洩半成品狀態給下游、不產生多餘 trace）。
預設 retries=0 → 與今天行為完全一致。
"""
from __future__ import annotations

from polaris.graph.nodes.trace import traced


class _Api(Exception):
    """帶狀態碼的假例外，503 → is_transient 判為可重試。"""

    def __init__(self, code: int) -> None:
        super().__init__(str(code))
        self.code = code


class TestTracedRetry:
    def test_retries_transient_then_succeeds_single_ok_trace(self, no_retry_sleep):
        calls = {"n": 0}

        @traced("flaky", retries=2)
        def node(state):
            calls["n"] += 1
            if calls["n"] < 3:
                raise _Api(503)
            return {"value": 42}

        patch = node({"query": "x"})
        assert calls["n"] == 3  # 失敗兩次後第三次成功
        assert patch["value"] == 42
        assert "halt" not in patch
        traces = patch["trace"]
        assert len(traces) == 1  # 整個節點只 emit 一筆 trace，不因重試而暴增
        assert traces[0].status == "ok"
        assert traces[0].node_name == "flaky"

    def test_exhausts_retries_then_halts_single_error_trace(self, no_retry_sleep):
        calls = {"n": 0}

        @traced("always_fail", retries=2)
        def node(state):
            calls["n"] += 1
            raise _Api(503)

        patch = node({"query": "x"})
        assert calls["n"] == 3  # retries=2 → 共 3 次嘗試
        assert patch["halt"] is True
        assert "value" not in patch  # FR-009：不洩半成品狀態
        traces = patch["trace"]
        assert len(traces) == 1
        assert traces[0].status == "error"

    def test_permanent_error_not_retried(self):
        calls = {"n": 0}

        @traced("perm", retries=2)
        def node(state):
            calls["n"] += 1
            raise ValueError("empty query")

        patch = node({"query": ""})
        assert calls["n"] == 1  # 永久性（ValueError）→ 不重試
        assert patch["halt"] is True
        assert patch["trace"][0].status == "error"

    def test_default_retries_zero_keeps_single_attempt(self):
        calls = {"n": 0}

        @traced("default")
        def node(state):
            calls["n"] += 1
            raise _Api(503)

        patch = node({"query": "x"})
        assert calls["n"] == 1  # 預設 retries=0 → 僅一次嘗試（行為不變）
        assert patch["halt"] is True

    def test_decorator_exposes_retry_metadata(self):
        @traced("x", retries=3)
        def node(state):
            return {}

        assert node._traced_retries == 3
        assert node._traced_node == "x"


class TestNodeRetryWiring:
    """D7：哪些節點接了保險絲（retries=2）。I/O-bound 節點啟用、其餘為 0。"""

    def test_io_bound_nodes_have_retry(self):
        from polaris.graph.nodes import stubs

        # retriever / calculator 接 R4 真實向量檢索 / BigQuery I/O → 保險絲
        assert stubs.retriever._traced_retries == 2
        assert stubs.calculator._traced_retries == 2

    def test_llm_and_pure_nodes_have_no_node_level_retry(self):
        from polaris.graph.nodes import stubs

        # planner / writer 已由 Tier 1（LLM 邊界）覆蓋，避免雙重重試
        assert stubs.planner._traced_retries == 0
        assert stubs.writer._traced_retries == 0
        # compliance 純確定性，無 I/O
        assert stubs.compliance._traced_retries == 0
