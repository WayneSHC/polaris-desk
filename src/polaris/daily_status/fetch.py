"""GitHub 活動抓取：GitHubClient（唯一網路類別）+ fetch_events。

⚠️ 一律用 REST **list** 端點（非 Search API）做時間篩選。原因：GitHub Actions 的
內建 `GITHUB_TOKEN` 對 `/search/issues` 會回 200 但空結果（即使資料已索引、用 PAT
查得到），導致每日報告全 0。REST list 端點對 `GITHUB_TOKEN` 正常，故改抓「最近更新的
前 100 筆」再於程式內用時間窗篩選。
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .timewindow import to_github_iso

API = "https://api.github.com"
UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class Event:
    kind: str  # "pr_merged" | "pr_opened" | "review" | "issue_closed" | "commit"
    author: str  # GitHub login
    number: int | None  # PR/issue 編號（commit 為 None）
    title: str  # PR/issue 標題（commit 為 ""）


class GitHubClient:
    """最小 REST client：get/post/patch，回傳已解析 JSON（dict 或 list）。"""

    def __init__(self, token: str) -> None:
        self._token = token

    def _req(self, method: str, url: str, payload: dict | None = None) -> Any:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "polaris-daily-status")
        if payload is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (固定 https)
            return json.loads(resp.read().decode())

    def get(self, url: str) -> Any:
        return self._req("GET", url)

    def post(self, url: str, payload: dict) -> Any:
        return self._req("POST", url, payload)

    def patch(self, url: str, payload: dict) -> Any:
        return self._req("PATCH", url, payload)


def _parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _in_window(iso_str: str | None, start_utc: datetime, end_utc: datetime) -> bool:
    return bool(iso_str) and start_utc <= _parse_iso(iso_str) < end_utc


def fetch_events(
    client: Any, repo: str, start_utc: datetime, end_utc: datetime
) -> list[Event]:
    start, end = to_github_iso(start_utc), to_github_iso(end_utc)
    events: list[Event] = []

    # PRs：抓最近更新的前 100 筆（per_page=100，不分頁——plan 假設 <100 PR 動到/日）。
    prs = client.get(
        f"{API}/repos/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=100"
    )
    for pr in prs if isinstance(prs, list) else []:
        login = (pr.get("user") or {}).get("login")
        if not login:
            continue
        num, title = pr["number"], pr["title"]
        if _in_window(pr.get("merged_at"), start_utc, end_utc):
            events.append(Event("pr_merged", login, num, title))
        # 進行中 = 仍 open 且窗內開啟（state=open 才算，避免同日 open→merge 重複計）
        if pr.get("state") == "open" and _in_window(pr.get("created_at"), start_utc, end_utc):
            events.append(Event("pr_opened", login, num, title))
        # reviews：只對窗內有更新的 PR 抓其 reviews（N+1，team 規模可接受）。
        if _in_window(pr.get("updated_at"), start_utc, end_utc):
            reviews = client.get(f"{API}/repos/{repo}/pulls/{num}/reviews?per_page=100")
            for r in reviews if isinstance(reviews, list) else []:
                reviewer = (r.get("user") or {}).get("login")
                if reviewer and _in_window(r.get("submitted_at"), start_utc, end_utc):
                    events.append(Event("review", reviewer, num, title))

    # 關閉的 issue：since 先粗篩（updated_at>=start），再用 closed_at 精篩；排除 PR。
    issues = client.get(
        f"{API}/repos/{repo}/issues?state=closed&since={start}"
        "&sort=updated&direction=desc&per_page=100"
    )
    for it in issues if isinstance(issues, list) else []:
        if "pull_request" in it:  # /issues 會混入 PR，排除
            continue
        login = (it.get("user") or {}).get("login")
        if login and _in_window(it.get("closed_at"), start_utc, end_utc):
            events.append(Event("issue_closed", login, it["number"], it["title"]))

    # commits（REST，對 GITHUB_TOKEN 一向正常；per_page=100 不分頁）。
    commits = client.get(f"{API}/repos/{repo}/commits?since={start}&until={end}&per_page=100")
    for c in commits if isinstance(commits, list) else []:
        login = (c.get("author") or {}).get("login")
        if login:
            events.append(Event("commit", login, None, ""))

    return events
