"""Daily Status Sync 單元測試（roles / timewindow / aggregate / render / publish / fetch）。"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from polaris.daily_status import roles as R


def test_role_for_known_username_case_insensitive():
    role = R.role_for("WayneSHC")
    assert role is not None
    assert role.code == "R2"
    assert role.name == "施惠棋"
    assert R.role_for("wayneshc") == role  # 大小寫不敏感


def test_role_for_unknown_returns_none():
    assert R.role_for("some-random-bot") is None


def test_all_roles_ordered_r1_to_r7():
    assert [r.code for r in R.ROLES] == ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]


from polaris.daily_status import timewindow as TW


def test_yesterday_window_normal_day():
    # 台北 2026-06-03 → 報告「台北 2026-06-02 全天」
    start, end = TW.yesterday_window(date(2026, 6, 3))
    assert start == datetime(2026, 6, 1, 16, 0, tzinfo=ZoneInfo("UTC"))  # 台北 06-02 00:00
    assert end == datetime(2026, 6, 2, 16, 0, tzinfo=ZoneInfo("UTC"))   # 台北 06-03 00:00


def test_yesterday_window_month_boundary():
    # 台北 2026-06-01 → 昨日 = 台北 2026-05-31
    start, end = TW.yesterday_window(date(2026, 6, 1))
    assert start == datetime(2026, 5, 30, 16, 0, tzinfo=ZoneInfo("UTC"))
    assert end == datetime(2026, 5, 31, 16, 0, tzinfo=ZoneInfo("UTC"))


def test_to_github_iso_format():
    dt = datetime(2026, 6, 2, 16, 0, tzinfo=ZoneInfo("UTC"))
    assert TW.to_github_iso(dt) == "2026-06-02T16:00:00Z"


from polaris.daily_status import fetch as F


class FakeClient:
    """以 URL 子字串對應 canned JSON；記錄所有請求。網路 0、隨機 0。"""

    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = routes
        self.gets: list[str] = []
        self.posts: list[tuple[str, dict]] = []
        self.patches: list[tuple[str, dict]] = []

    def _match(self, url: str) -> object:
        for key, val in self.routes.items():
            if key in url:
                return val
        return {"items": []} if "search" in url else []

    def get(self, url: str) -> object:
        self.gets.append(url)
        return self._match(url)

    def post(self, url: str, payload: dict) -> object:
        self.posts.append((url, payload))
        return {"number": 123}

    def patch(self, url: str, payload: dict) -> object:
        self.patches.append((url, payload))
        return {"number": 123}


def test_fetch_events_collects_kinds():
    routes = {
        "is:pr+is:merged": {"items": [{"user": {"login": "WayneSHC"}, "number": 42, "title": "merge X"}]},
        "is:pr+created": {"items": [{"user": {"login": "holajennytw"}, "number": 44, "title": "wip Y"}]},
        "is:issue+is:closed": {"items": [{"user": {"login": "WayneSHC"}, "number": 7, "title": "close Z"}]},
        "/commits": [{"author": {"login": "WayneSHC"}}, {"author": {"login": "holajennytw"}}],
        "is:pr+updated": {"items": []},  # 無更新 PR → 不抓 reviews
    }
    client = FakeClient(routes)
    start = datetime(2026, 6, 1, 16, 0, tzinfo=ZoneInfo("UTC"))
    end = datetime(2026, 6, 2, 16, 0, tzinfo=ZoneInfo("UTC"))
    events = F.fetch_events(client, "WayneSHC/polaris-desk", start, end)

    kinds = sorted(e.kind for e in events)
    assert kinds == ["commit", "commit", "issue_closed", "pr_merged", "pr_opened"]
    merged = [e for e in events if e.kind == "pr_merged"][0]
    assert merged.author == "WayneSHC" and merged.number == 42
