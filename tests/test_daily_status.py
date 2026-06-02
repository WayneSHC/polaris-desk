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
