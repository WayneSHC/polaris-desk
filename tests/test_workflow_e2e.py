"""US1 — End-to-end LangGraph workflow tests (T006/T007/T008).

對應 spec SC-001 / SC-002 / SC-004 / SC-006。
"""
from __future__ import annotations

import time

import pytest

SAMPLE_QUERY = "台積電 2025 Q1 營收 YoY 是多少？"


@pytest.fixture
def app():
    from polaris.graph.workflow import build_workflow

    return build_workflow()


# ---------------------------------------------------------------------------
# T006 — happy path（SC-001 / SC-002）
# ---------------------------------------------------------------------------

class TestE2EHappyPath:

    def test_returns_answer_and_citations(self, app):
        """FR-004：最終輸出含 answer 與 citations（≥ 1 條）。"""
        from polaris.graph.state import Citation

        result = app.invoke({"query": SAMPLE_QUERY})

        assert isinstance(result.get("answer"), str)
        assert len(result["answer"]) > 0
        citations = result.get("citations") or []
        assert len(citations) >= 1
        for c in citations:
            assert isinstance(c, Citation)
            assert c.source_id and c.snippet

    def test_trace_has_all_five_nodes_in_order(self, app):
        """SC-002：5 節點齊全、status 全 ok、依固定順序執行。"""
        result = app.invoke({"query": SAMPLE_QUERY})

        names = [t.node_name for t in result.get("trace", [])]
        assert names == ["planner", "retriever", "calculator", "writer", "compliance"]
        assert all(t.status == "ok" for t in result["trace"])

    def test_compliance_status_passed_on_happy_path(self, app):
        """合規草稿走 compliance 節點後 status = passed。"""
        result = app.invoke({"query": SAMPLE_QUERY})
        assert result.get("compliance_status") == "passed"

    def test_no_halt_on_happy_path(self, app):
        result = app.invoke({"query": SAMPLE_QUERY})
        # halt 可能未設或為 False，兩種都接受
        assert not result.get("halt", False)

    def test_node_patches_populate_state(self, app):
        """節點各自的輸出 (plan/contexts/calculations/draft) 都有出現。"""
        result = app.invoke({"query": SAMPLE_QUERY})
        assert result.get("plan")
        assert result.get("contexts")
        assert result.get("calculations")
        assert result.get("draft")


# ---------------------------------------------------------------------------
# T007 — determinism（SC-006）
# ---------------------------------------------------------------------------

class TestE2EDeterminism:
    """同問題連跑 3 次，除了 elapsed_ms，其他欄位 byte-identical。"""

    def test_three_runs_identical(self, app):
        runs = [app.invoke({"query": SAMPLE_QUERY}) for _ in range(3)]

        # 純資料欄位：完全相同
        for key in ("answer", "plan", "contexts", "calculations",
                    "draft", "citations", "compliance_status"):
            values = [r.get(key) for r in runs]
            assert values[0] == values[1] == values[2], (
                f"non-deterministic field: {key} → {values}"
            )

    def test_trace_structure_identical_except_elapsed_ms(self, app):
        runs = [app.invoke({"query": SAMPLE_QUERY}) for _ in range(3)]

        traces = [r["trace"] for r in runs]
        assert len(traces[0]) == len(traces[1]) == len(traces[2])

        for i in range(len(traces[0])):
            t0, t1, t2 = traces[0][i], traces[1][i], traces[2][i]
            for attr in ("node_name", "status", "input_keys",
                         "output_keys", "error_message"):
                v = (getattr(t0, attr), getattr(t1, attr), getattr(t2, attr))
                assert v[0] == v[1] == v[2], f"trace[{i}].{attr} not deterministic: {v}"


# ---------------------------------------------------------------------------
# T008 — runtime budget（SC-004）
# ---------------------------------------------------------------------------

class TestE2ERuntime:

    def test_under_10_seconds(self, app):
        start = time.perf_counter()
        app.invoke({"query": SAMPLE_QUERY})
        elapsed = time.perf_counter() - start
        # stub mode 實際應 < 100ms；10 秒上限是 spec SC-004 的寬鬆預算
        assert elapsed < 10.0, f"e2e took {elapsed:.3f}s, exceeds 10s budget"


# ---------------------------------------------------------------------------
# T016 — US2 Compliance e2e（SC-003）
# ---------------------------------------------------------------------------

class TestE2EComplianceBlocks:
    """End-to-end：writer 草稿含買賣建議 → compliance 節點攔截 → 最終 answer 為固定安全訊息。"""

    def test_buysell_draft_results_in_blocked_safe_message(self, monkeypatch):
        from polaris.graph.compliance import BUYSELL_KEYWORDS, SAFE_MESSAGE
        from polaris.graph.nodes import stubs
        from polaris.graph.nodes.trace import traced
        from polaris.graph.state import Citation

        @traced("writer")
        def buysell_writer(state):
            return {
                "draft": "依據法說會分析，我建議買進台積電。",
                "citations": [
                    Citation(source_id="stub-x", snippet="snippet", origin="stub")
                ],
            }

        monkeypatch.setattr(stubs, "writer", buysell_writer)

        from polaris.graph.workflow import build_workflow

        app = build_workflow()
        result = app.invoke({"query": "should I buy TSMC now?"})

        # SC-003：最終 answer 不可含任何 6 條關鍵字
        ans = result.get("answer", "")
        for kw in BUYSELL_KEYWORDS:
            assert kw not in ans, f"final answer contains forbidden keyword: {kw!r}"
        assert ans == SAFE_MESSAGE
        assert result.get("compliance_status") == "blocked"

    def test_compliance_node_executes_normally_on_block(self, monkeypatch):
        """compliance 節點本身是 status=ok 跑完攔截、不是 error。trace 仍 5 筆全 ok。"""
        from polaris.graph.nodes import stubs
        from polaris.graph.nodes.trace import traced
        from polaris.graph.state import Citation

        @traced("writer")
        def buysell_writer(state):
            return {
                "draft": "加碼台積電的好時機。",
                "citations": [
                    Citation(source_id="stub-x", snippet="snippet", origin="stub")
                ],
            }

        monkeypatch.setattr(stubs, "writer", buysell_writer)

        from polaris.graph.workflow import build_workflow

        app = build_workflow()
        result = app.invoke({"query": "q"})

        names = [t.node_name for t in result.get("trace", [])]
        assert names == ["planner", "retriever", "calculator", "writer", "compliance"]
        assert all(t.status == "ok" for t in result["trace"])
        assert not result.get("halt", False)
