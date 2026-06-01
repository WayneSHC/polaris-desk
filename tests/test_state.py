"""T004 — 測試 src/polaris/graph/state.py 的 Citation / NodeTrace / ResearchState。

對應 spec FR-004 / FR-006 / Key Entities，data-model.md 完整定義。
"""
from __future__ import annotations

import operator
from typing import get_type_hints

import pytest
from pydantic import ValidationError


# ============================================================================
# Citation
# ============================================================================

class TestCitation:
    """Citation 必填欄位 + origin enum 限制。"""

    def test_citation_minimal_valid(self):
        from polaris.graph.state import Citation
        c = Citation(source_id="stub-001", snippet="some text", origin="stub")
        assert c.source_id == "stub-001"
        assert c.snippet == "some text"
        assert c.origin == "stub"

    def test_citation_rejects_empty_source_id(self):
        from polaris.graph.state import Citation
        with pytest.raises(ValidationError):
            Citation(source_id="", snippet="x", origin="stub")

    def test_citation_rejects_empty_snippet(self):
        from polaris.graph.state import Citation
        with pytest.raises(ValidationError):
            Citation(source_id="x", snippet="", origin="stub")

    def test_citation_rejects_unknown_origin(self):
        from polaris.graph.state import Citation
        with pytest.raises(ValidationError):
            Citation(source_id="x", snippet="y", origin="made-up-source")

    def test_citation_accepts_all_documented_origins(self):
        from polaris.graph.state import Citation
        for origin in ("stub", "bm25", "embedding", "colpali", "rerank", "news"):
            c = Citation(source_id="x", snippet="y", origin=origin)
            assert c.origin == origin


# ============================================================================
# NodeTrace
# ============================================================================

class TestNodeTrace:
    """NodeTrace 各 status 的合法欄位組合 + error_message 互斥規則。"""

    def test_nodetrace_ok_minimal(self):
        from polaris.graph.state import NodeTrace
        t = NodeTrace(
            node_name="planner",
            status="ok",
            input_keys=["query"],
            output_keys=["plan"],
            elapsed_ms=5,
        )
        assert t.status == "ok"
        assert t.error_message is None

    def test_nodetrace_error_requires_message(self):
        """status=error 必須有 error_message（非 None 且非空）。"""
        from polaris.graph.state import NodeTrace
        with pytest.raises(ValidationError):
            NodeTrace(
                node_name="retriever",
                status="error",
                input_keys=["query"],
                output_keys=[],
                elapsed_ms=1,
                # 缺 error_message
            )

    def test_nodetrace_ok_rejects_error_message(self):
        """status=ok 時，error_message 必須為 None（不可同時存在）。"""
        from polaris.graph.state import NodeTrace
        with pytest.raises(ValidationError):
            NodeTrace(
                node_name="planner",
                status="ok",
                input_keys=["query"],
                output_keys=["plan"],
                elapsed_ms=1,
                error_message="boom",
            )

    def test_nodetrace_skipped_no_error(self):
        from polaris.graph.state import NodeTrace
        t = NodeTrace(
            node_name="writer",
            status="skipped",
            input_keys=["query", "plan"],
            output_keys=[],
            elapsed_ms=0,
        )
        assert t.status == "skipped"
        assert t.error_message is None

    def test_nodetrace_rejects_unknown_status(self):
        from polaris.graph.state import NodeTrace
        with pytest.raises(ValidationError):
            NodeTrace(
                node_name="x",
                status="???",
                input_keys=[],
                output_keys=[],
                elapsed_ms=0,
            )

    def test_nodetrace_elapsed_ms_must_be_non_negative(self):
        from polaris.graph.state import NodeTrace
        with pytest.raises(ValidationError):
            NodeTrace(
                node_name="x",
                status="ok",
                input_keys=[],
                output_keys=[],
                elapsed_ms=-1,
            )


# ============================================================================
# ResearchState (TypedDict)
# ============================================================================

class TestResearchState:
    """ResearchState 是 LangGraph 用的 TypedDict — 驗證 keys 與型別 hint。"""

    def test_state_has_required_keys(self):
        from polaris.graph.state import ResearchState
        hints = get_type_hints(ResearchState, include_extras=True)
        # 對齊 data-model.md 表格
        expected = {
            "query", "plan", "contexts", "calculations", "draft", "answer",
            "citations", "compliance_status", "trace", "halt",
        }
        assert expected.issubset(set(hints.keys())), (
            f"missing keys: {expected - set(hints.keys())}"
        )

    def test_state_query_is_str(self):
        from polaris.graph.state import ResearchState
        hints = get_type_hints(ResearchState)
        assert hints["query"] is str

    def test_state_halt_is_bool(self):
        from polaris.graph.state import ResearchState
        hints = get_type_hints(ResearchState)
        assert hints["halt"] is bool

    def test_state_trace_uses_add_reducer(self):
        """trace 欄位必須是 Annotated[list[NodeTrace], operator.add]，
        否則 LangGraph 不會累加多次 patch — 直接破 FR-006 + SC-002。
        """
        from polaris.graph.state import ResearchState, NodeTrace
        hints = get_type_hints(ResearchState, include_extras=True)
        trace_hint = hints["trace"]
        # Annotated 物件的 metadata 在 __metadata__
        assert hasattr(trace_hint, "__metadata__"), (
            "trace must be Annotated to carry LangGraph reducer"
        )
        # __metadata__ 至少要有一個能合併 list 的 callable
        # 接受 operator.add 或任何能把兩個 list 合起來的 callable
        assert any(
            callable(m) and m([1], [2]) == [1, 2]
            for m in trace_hint.__metadata__
        ), "trace reducer must merge lists (e.g., operator.add)"

    def test_initial_state_only_needs_query(self):
        """LangGraph 入口允許只填 query — 其他欄位 total=False 應預設不存在。"""
        from polaris.graph.state import ResearchState
        # TypedDict 不會在 runtime 強制鍵；確認類別宣告為 total=False
        # 透過 __total__ 屬性查驗
        assert getattr(ResearchState, "__total__", True) is False, (
            "ResearchState 必須是 total=False，讓 LangGraph 漸進填入"
        )
