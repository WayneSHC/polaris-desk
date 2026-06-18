"""polaris.user_store — per-user 活動紀錄 + 訂閱（Firestore）。

R7-1 決議：登入後把每次研究 / 同業比較存成可**完整還原**的 session（B 級，存整包
``result``），存進 Firestore；訂閱清單與紀錄共用同一 ``users/{uid}`` doc。

Firestore 重相依**延遲 import**，不進 CI 必經路徑——本測試注入 FakeFirestore
（最小可鏈式 fake），0 GCP 外呼、0 金鑰。驗：寫入/列出/單筆還原/訂閱 roundtrip/
使用者隔離。
"""
from __future__ import annotations

from polaris.user_store import UserStore


# ── 最小 Firestore fake（支援 UserStore 用到的 collection/document 鏈）──────────
class FakeSnap:
    def __init__(self, id_, fields):
        self.id = id_
        self._fields = fields

    @property
    def exists(self):
        return self._fields is not None

    def to_dict(self):
        return dict(self._fields) if self._fields is not None else None


class FakeDoc:
    def __init__(self):
        self.fields = None
        self.subcols: dict = {}


class FakeDocRef:
    def __init__(self, node: FakeDoc, id_: str):
        self._node = node
        self.id = id_

    def set(self, data, merge=False):
        if merge and self._node.fields:
            self._node.fields = {**self._node.fields, **data}
        else:
            self._node.fields = dict(data)

    def get(self):
        return FakeSnap(self.id, self._node.fields)

    def collection(self, name):
        return self._node.subcols.setdefault(name, FakeCollection())


class FakeCollection:
    def __init__(self):
        self.docs: dict = {}
        self._auto = 0

    def document(self, id_=None):
        if id_ is None:
            self._auto += 1
            id_ = f"auto{self._auto}"
        node = self.docs.setdefault(id_, FakeDoc())
        return FakeDocRef(node, id_)

    def stream(self):
        return [FakeSnap(i, d.fields) for i, d in self.docs.items() if d.fields is not None]


class FakeFirestore:
    def __init__(self):
        self.root: dict = {}

    def collection(self, name):
        return self.root.setdefault(name, FakeCollection())


def make_store():
    class _S:
        gcp_project = "test-proj"
    return UserStore(_S(), client=FakeFirestore())


SAMPLE = {
    "origin": "research",
    "query": "台積電 2026Q1 法說重點",
    "tickers": ["2330"],
    "result": {"final_answer": "...", "evidence": [], "react_steps": [], "citations": []},
}


class TestSessions:
    def test_save_returns_id_and_get_restores_full_result(self):
        store = make_store()
        rid = store.save_session("u1", SAMPLE)
        assert rid
        got = store.get_session("u1", rid)
        assert got["result"]["final_answer"] == "..."   # B 級：整包 result 還原
        assert got["query"] == "台積電 2026Q1 法說重點"
        assert got["id"] == rid

    def test_save_sets_created_at_when_absent(self):
        store = make_store()
        rid = store.save_session("u1", SAMPLE)
        assert store.get_session("u1", rid).get("created_at")

    def test_list_returns_saved_newest_first(self):
        store = make_store()
        store.save_session("u1", {**SAMPLE, "query": "old", "created_at": "2026-06-01T00:00:00"})
        store.save_session("u1", {**SAMPLE, "query": "new", "created_at": "2026-06-18T00:00:00"})
        out = store.list_sessions("u1")
        assert [s["query"] for s in out] == ["new", "old"]

    def test_list_respects_limit(self):
        store = make_store()
        for i in range(5):
            store.save_session("u1", {**SAMPLE, "created_at": f"2026-06-0{i}T00:00:00"})
        assert len(store.list_sessions("u1", limit=2)) == 2

    def test_get_unknown_session_returns_none(self):
        assert make_store().get_session("u1", "nope") is None

    def test_sessions_isolated_per_user(self):
        store = make_store()
        store.save_session("alice", SAMPLE)
        assert store.list_sessions("bob") == []


class TestSubscriptions:
    def test_default_empty(self):
        assert make_store().get_subs("u1") == []

    def test_set_then_get_roundtrip(self):
        store = make_store()
        store.set_subs("u1", ["2330", "2454"])
        assert store.get_subs("u1") == ["2330", "2454"]

    def test_subs_isolated_per_user(self):
        store = make_store()
        store.set_subs("alice", ["2330"])
        assert store.get_subs("bob") == []

    def test_set_subs_merge_keeps_sessions(self):
        store = make_store()
        rid = store.save_session("u1", SAMPLE)
        store.set_subs("u1", ["2330"])
        # 訂閱寫在 users/{uid} doc，sessions 子集合不該被覆蓋掉
        assert store.get_session("u1", rid) is not None
        assert store.get_subs("u1") == ["2330"]
