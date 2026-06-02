"""維護單一滾動 Daily Status Issue（找 / 更新 / 建立）。"""
from __future__ import annotations

from typing import Any

from .fetch import API


def find_rolling_issue(client: Any, repo: str, label: str) -> dict | None:
    url = f"{API}/repos/{repo}/issues?labels={label}&state=open&per_page=100"
    items = client.get(url)
    items = items if isinstance(items, list) else []
    return items[0] if items else None


def upsert_rolling_issue(
    client: Any, repo: str, label: str, title: str, body: str
) -> int:
    existing = find_rolling_issue(client, repo, label)
    if existing is not None:
        num = existing["number"]
        client.patch(f"{API}/repos/{repo}/issues/{num}", {"body": body})
        return int(num)
    created = client.post(
        f"{API}/repos/{repo}/issues",
        {"title": title, "body": body, "labels": [label]},
    )
    return int(created["number"])
