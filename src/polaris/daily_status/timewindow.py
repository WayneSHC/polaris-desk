"""計算 Asia/Taipei『昨日』的 UTC 時間區間。"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
UTC = ZoneInfo("UTC")


def yesterday_window(today_taipei: date) -> tuple[datetime, datetime]:
    """回傳 (start_utc, end_utc)：台北『昨日 00:00』到『今日 00:00』對應的 UTC 區間。"""
    start_local = datetime.combine(today_taipei - timedelta(days=1), time.min, tzinfo=TAIPEI)
    end_local = datetime.combine(today_taipei, time.min, tzinfo=TAIPEI)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def to_github_iso(dt: datetime) -> str:
    """GitHub REST/Search 用的 ISO8601（UTC、結尾 Z）。"""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
