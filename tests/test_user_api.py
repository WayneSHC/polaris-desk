"""polaris.api — 使用者紀錄 / 訂閱端點（R7-1：登入後活動歷史 + 訂閱）。

驗：未登入（無 Bearer）→ 401（匿名不得讀寫個人資料）；登入（override current_user）
+ 注入 fake Firestore store → POST /history 寫入、GET /history 列出、GET /history/{id}
完整還原、/subscriptions roundtrip。token-free：不連 GCP、不需金鑰。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from polaris import api
from polaris.auth import current_user
from polaris.user_store import UserStore


# ── 最小 Firestore fake（同 test_user_store；各測試檔自含，免跨檔 import）──────
class _Snap:
    def __init__(self, id_, fields):
        self.id, self._f = id_, fields

    @property
    def exists(self):
        return self._f is not None

    def to_dict(self):
        return dict(self._f) if self._f is not None else None


class _Node:
    def __init__(self):
        self.fields = None
        self.subcols: dict = {}


class _DocRef:
    def __init__(self, node, id_):
        self._n, self.id = node, id_

    def set(self, data, merge=False):
        self._n.fields = {**self._n.fields, **data} if (merge and self._n.fields) else dict(data)

    def get(self):
        return _Snap(self.id, self._n.fields)

    def collection(self, name):
        return self._n.subcols.setdefault(name, _Col())


class _Col:
    def __init__(self):
        self.docs: dict = {}
        self._auto = 0

    def document(self, id_=None):
        if id_ is None:
            self._auto += 1
            id_ = f"auto{self._auto}"
        return _DocRef(self.docs.setdefault(id_, _Node()), id_)

    def stream(self):
        return [_Snap(i, n.fields) for i, n in self.docs.items() if n.fields is not None]


class FakeFirestore:
    def __init__(self):
        self.root: dict = {}

    def collection(self, name):
        return self.root.setdefault(name, _Col())


@pytest.fixture
def client() -> TestClient:
    return TestClient(api.app)


@pytest.fixture
def store(monkeypatch) -> UserStore:
    class _S:
        gcp_project = "test-proj"
    s = UserStore(_S(), client=FakeFirestore())
    monkeypatch.setattr(api, "_user_store", s)
    return s


@pytest.fixture
def authed():
    """以 sub=u1 登入；測試後清掉 override。"""
    api.app.dependency_overrides[current_user] = lambda: {"sub": "u1"}
    yield
    api.app.dependency_overrides.pop(current_user, None)


HIST = {
    "origin": "research",
    "query": "台積電 2026Q1 法說重點",
    "tickers": ["2330"],
    "result": {"final_answer": "毛利率約 X", "evidence": [], "react_steps": [], "citations": []},
}


class TestHistoryAuth:
    def test_post_history_anonymous_is_401(self, client, store):
        assert client.post("/history", json=HIST).status_code == 401

    def test_get_history_anonymous_is_401(self, client, store):
        assert client.get("/history").status_code == 401

    def test_subscriptions_anonymous_is_401(self, client, store):
        assert client.get("/subscriptions").status_code == 401
        assert client.post("/subscriptions", json={"tickers": ["2330"]}).status_code == 401


class TestHistoryFlow:
    def test_post_then_list_and_restore(self, client, store, authed):
        rid = client.post("/history", json=HIST).json()["record_id"]
        assert rid

        listing = client.get("/history").json()
        assert any(s["id"] == rid and s["query"] == HIST["query"] for s in listing)

        full = client.get(f"/history/{rid}").json()
        assert full["result"]["final_answer"] == "毛利率約 X"  # B 級完整還原

    def test_get_unknown_history_is_404(self, client, store, authed):
        assert client.get("/history/does-not-exist").status_code == 404

    def test_history_is_scoped_to_logged_in_user(self, client, store, authed):
        client.post("/history", json=HIST)
        # 直接用另一使用者查 store → 看不到 u1 的紀錄
        assert store.list_sessions("someone-else") == []


class TestSubscriptionsFlow:
    def test_roundtrip(self, client, store, authed):
        assert client.get("/subscriptions").json()["tickers"] == []
        r = client.post("/subscriptions", json={"tickers": ["2330", "2454"]})
        assert r.json()["tickers"] == ["2330", "2454"]
        assert client.get("/subscriptions").json()["tickers"] == ["2330", "2454"]


class TestNoRegressionAnonymous:
    def test_ask_still_works_without_login(self, client):
        """匿名降級：核心 /ask 不需登入（保斷網備援 / token-free）。"""
        r = client.post("/ask", json={"query": "台積電 2025Q1 毛利率？"})
        assert r.status_code == 200
