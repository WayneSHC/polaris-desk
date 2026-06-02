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
