"""T021 — US3 節點替換驗證：FR-007 / SC-005。

驗證「workflow 結構與節點實作分離」這個架構承諾：

- 把任一 stub 節點換成行為不同的版本，**workflow.py 檔案不被改動**
- 新節點行為反映在最終輸出（state + trace）
- 這保證 R3 W1 D2+ 把真 agent 推進來時，只動 ``nodes/`` 底下、不動 wiring

註：本檔不需要任何新的 production code；若這些測試 fail，代表 US1 的
``stubs.py`` / ``workflow.py`` 拆分有問題，必須回頭調整（**不可**靠改
``workflow.py`` 來通過）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

WORKFLOW_PATH = Path(__file__).parent.parent / "src" / "polaris" / "graph" / "workflow.py"


def _hash_workflow() -> str:
    """SHA-256 of workflow.py — must be identical before/after node swap."""
    return hashlib.sha256(WORKFLOW_PATH.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 1. workflow.py 不被改 — 純檔案完整性檢查
# ---------------------------------------------------------------------------

class TestWorkflowFileIntegrity:
    """SC-005：節點替換的「diff = 0 行」要求，本檔以 hash 檢查落實。"""

    def test_workflow_file_exists(self):
        assert WORKFLOW_PATH.exists(), f"workflow.py not found at {WORKFLOW_PATH}"

    def test_hash_unchanged_after_planner_swap(self, monkeypatch):
        from polaris.graph.nodes import stubs
        from polaris.graph.nodes.trace import traced

        before = _hash_workflow()

        @traced("planner")
        def planner_v2(state):
            return {"plan": ["v2 step A", "v2 step B"]}

        monkeypatch.setattr(stubs, "planner", planner_v2)

        from polaris.graph.workflow import build_workflow
        app = build_workflow()
        app.invoke({"query": "TSMC Q1"})

        after = _hash_workflow()
        assert before == after, (
            f"workflow.py was modified during node swap: "
            f"before={before[:16]}... after={after[:16]}..."
        )

    def test_hash_unchanged_after_calculator_swap(self, monkeypatch):
        """換另一個節點也一樣不能改 workflow.py。"""
        from polaris.graph.nodes import stubs
        from polaris.graph.nodes.trace import traced

        before = _hash_workflow()

        @traced("calculator")
        def calculator_v2(state):
            return {"calculations": {"YoY_pct": 99.99}}

        monkeypatch.setattr(stubs, "calculator", calculator_v2)

        from polaris.graph.workflow import build_workflow
        app = build_workflow()
        app.invoke({"query": "TSMC Q1"})

        after = _hash_workflow()
        assert before == after


# ---------------------------------------------------------------------------
# 2. 換掉 stub 之後，新行為要反映在輸出
# ---------------------------------------------------------------------------

class TestSwappedNodeBehaviorReflected:
    """若 swap 不能改變輸出，那「替換」根本沒生效，US3 失敗。"""

    def test_planner_swap_changes_plan_in_state(self, monkeypatch):
        from polaris.graph.nodes import stubs
        from polaris.graph.nodes.trace import traced

        @traced("planner")
        def planner_v2(state):
            return {"plan": ["v2 step A", "v2 step B"]}

        monkeypatch.setattr(stubs, "planner", planner_v2)

        from polaris.graph.workflow import build_workflow
        app = build_workflow()
        result = app.invoke({"query": "TSMC Q1"})

        assert result.get("plan") == ["v2 step A", "v2 step B"]
        # trace 第一筆仍是 planner，但其 output_keys 反映新 patch
        first = result["trace"][0]
        assert first.node_name == "planner"
        assert first.status == "ok"
        assert first.output_keys == ["plan"]

    def test_calculator_swap_changes_calculations_in_state(self, monkeypatch):
        from polaris.graph.nodes import stubs
        from polaris.graph.nodes.trace import traced

        @traced("calculator")
        def calculator_v2(state):
            return {"calculations": {"YoY_pct": 99.99, "marker": "v2"}}

        monkeypatch.setattr(stubs, "calculator", calculator_v2)

        from polaris.graph.workflow import build_workflow
        app = build_workflow()
        result = app.invoke({"query": "TSMC Q1"})

        calcs = result.get("calculations") or {}
        assert calcs.get("YoY_pct") == 99.99
        assert calcs.get("marker") == "v2"
