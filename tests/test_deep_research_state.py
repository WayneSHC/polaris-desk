"""D15 — Deep Research 狀態（polaris.graph.deep_research.state）。

ReActStep（審計步）、dedup_evidence（依 source_id 去重累積）、should_continue
（status + ≤max_loops 守門）。純資料/純函式，確定性可測。
"""
from __future__ import annotations

import pytest

from polaris.graph.deep_research import state as st
from polaris.graph.state import Citation


def _c(sid: str, snip: str = "片段") -> Citation:
    return Citation(source_id=sid, snippet=snip, origin="stub")


class TestReActStep:
    def test_fields_and_defaults(self):
        s = st.ReActStep(thought="t", action="search")
        assert s.thought == "t"
        assert s.action == "search"
        assert s.action_input == ""
        assert s.observation == ""

    def test_frozen(self):
        s = st.ReActStep(thought="t", action="finish")
        with pytest.raises(Exception):
            s.thought = "x"


class TestDedupEvidence:
    def test_merges(self):
        out = st.dedup_evidence([_c("a")], [_c("b")])
        assert [c.source_id for c in out] == ["a", "b"]

    def test_dedup_by_source_id(self):
        out = st.dedup_evidence([_c("a")], [_c("a"), _c("b")])
        assert [c.source_id for c in out] == ["a", "b"]

    def test_preserves_order(self):
        out = st.dedup_evidence([_c("a"), _c("b")], [_c("c")])
        assert [c.source_id for c in out] == ["a", "b", "c"]

    def test_empty_inputs(self):
        assert st.dedup_evidence([], []) == []
        assert [c.source_id for c in st.dedup_evidence([], [_c("a")])] == ["a"]


class TestShouldContinue:
    def test_running_under_cap_true(self):
        assert st.should_continue({"status": "running", "iteration": 0}) is True

    def test_answered_false(self):
        assert st.should_continue({"status": "answered", "iteration": 1}) is False

    def test_at_cap_false(self):
        assert st.should_continue({"status": "running", "iteration": 6}, max_loops=6) is False

    def test_under_cap_boundary_true(self):
        assert st.should_continue({"status": "running", "iteration": 5}, max_loops=6) is True

    def test_missing_fields_default_continue(self):
        assert st.should_continue({}) is True
