"""CLI：python -m polaris.daily_status

fetch → aggregate → render →（寫檔 + 更新滾動 Issue）。
只依賴 stdlib；Action 以 `PYTHONPATH=src python -m polaris.daily_status` 執行。
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from .aggregate import aggregate
from .fetch import GitHubClient, fetch_events
from .publish import find_rolling_issue, upsert_rolling_issue
from .render import merge_rolling_body, render_csv, render_day_block
from .timewindow import TAIPEI, yesterday_window


def _today_taipei() -> date:
    return datetime.now(TAIPEI).date()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="polaris.daily_status")
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "WayneSHC/polaris-desk"))
    p.add_argument("--out-dir", default="reports/daily")
    p.add_argument("--label", default="daily-status")
    p.add_argument("--issue-title", default="📊 Daily Status (rolling)")
    p.add_argument("--post-issue", action="store_true", help="更新/建立滾動 Issue")
    p.add_argument("--dry-run", action="store_true", help="只印不發、不寫檔")
    args = p.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token and not args.dry_run:
        print("ERROR: 需要環境變數 GITHUB_TOKEN", file=sys.stderr)
        return 1

    today = _today_taipei()
    start, end = yesterday_window(today)
    date_str = (today - timedelta(days=1)).isoformat()

    client = GitHubClient(token)
    events = fetch_events(client, args.repo, start, end)
    digest = aggregate(events, date_str)
    csv_text = render_csv(digest)
    day_block = render_day_block(digest)

    if args.dry_run:
        print(day_block)
        print()
        print(csv_text)
        return 0

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{date_str}.md").write_text(day_block, encoding="utf-8")
    (out / f"{date_str}.csv").write_text(csv_text, encoding="utf-8")

    if args.post_issue:
        existing = find_rolling_issue(client, args.repo, args.label)
        old_body = (existing or {}).get("body") or ""
        new_body = merge_rolling_body(old_body, day_block, date_str)
        num = upsert_rolling_issue(client, args.repo, args.label, args.issue_title, new_body)
        print(f"updated rolling issue #{num}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
