"""GitHub 活動抓取：GitHubClient（唯一網路類別）+ fetch_events。"""
from __future__ import annotations

import json
import urllib.parse
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


def _search(client: Any, query: str) -> list[dict]:
    # per_page=100, no pagination — plan assumes <100 items/kind/day at 7-person scale
    url = f"{API}/search/issues?q={urllib.parse.quote(query, safe=':+')}&per_page=100"
    data = client.get(url)
    return data.get("items", []) if isinstance(data, dict) else []


def _parse_iso(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def fetch_events(
    client: Any, repo: str, start_utc: datetime, end_utc: datetime
) -> list[Event]:
    start, end = to_github_iso(start_utc), to_github_iso(end_utc)
    rng = f"{start}..{end}"
    events: list[Event] = []

    for it in _search(client, f"repo:{repo}+is:pr+is:merged+merged:{rng}"):
        login = (it.get("user") or {}).get("login")
        if not login:
            continue
        events.append(Event("pr_merged", login, it["number"], it["title"]))
    for it in _search(client, f"repo:{repo}+is:pr+is:open+created:{rng}"):
        login = (it.get("user") or {}).get("login")
        if not login:
            continue
        events.append(Event("pr_opened", login, it["number"], it["title"]))
    for it in _search(client, f"repo:{repo}+is:issue+is:closed+closed:{rng}"):
        login = (it.get("user") or {}).get("login")
        if not login:
            continue
        events.append(Event("issue_closed", login, it["number"], it["title"]))

    commits = client.get(f"{API}/repos/{repo}/commits?since={start}&until={end}&per_page=100")  # per_page=100, no pagination — plan assumes <100 items/kind/day at 7-person scale
    for c in commits if isinstance(commits, list) else []:
        login = (c.get("author") or {}).get("login")
        if login:
            events.append(Event("commit", login, None, ""))

    # N+1: one /reviews GET per PR updated in window (fine at this team's scale)
    for pr in _search(client, f"repo:{repo}+is:pr+updated:{rng}"):
        num = pr["number"]
        reviews = client.get(f"{API}/repos/{repo}/pulls/{num}/reviews?per_page=100")
        for r in reviews if isinstance(reviews, list) else []:
            submitted, login = r.get("submitted_at"), (r.get("user") or {}).get("login")
            if submitted and login and start_utc <= _parse_iso(submitted) < end_utc:
                events.append(Event("review", login, num, pr["title"]))

    return events
