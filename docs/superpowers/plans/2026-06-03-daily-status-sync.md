# Daily Status Sync 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每天自動從 GitHub 活動推導各角色昨日進度，更新一張滾動 Issue 並產出 Notion 可匯入的 CSV，供 R1 PM 每日掌握與更新 Notion。

**Architecture:** 純函式（roles / timewindow / aggregate / render）與對外 I/O（fetch / publish）分離；CLI 串接後寫檔 + 更新 Issue。程式放 `src/polaris/daily_status/`，**只依賴 Python 標準函式庫**，故 GitHub Action 不需安裝重相依即可跑。`status` 分支的 git commit/push 由 workflow yaml 負責。

**Tech Stack:** Python 3.13、stdlib（`urllib`/`json`/`csv`/`zoneinfo`/`dataclasses`/`re`/`argparse`）、pytest、ruff、GitHub Actions、GitHub REST/Search API（內建 `GITHUB_TOKEN`）。

**對應 spec:** `docs/superpowers/specs/2026-06-03-daily-status-sync-design.md`

**開發分支:** `feat/daily-status-sync`（spec 已在此分支）。所有 commit 推這個分支，最後開 PR 併 `main`。

**已知限制（寫進 spec 假設）:** 每種活動每日假設 < 100 筆（不分頁）；7 人團隊規模不可能觸頂。Review 以「窗內更新過的 PR」之 reviews 計算。

---

### Task 1: 套件骨架 + roles.py（角色對照表）

**Files:**
- Create: `src/polaris/daily_status/__init__.py`
- Create: `src/polaris/daily_status/roles.py`
- Test: `tests/test_daily_status.py`

- [ ] **Step 1: 建空 `__init__.py`**

```python
"""Daily Status Sync — 從 GitHub 活動自動推導各角色每日進度。

只依賴 Python 標準函式庫，讓 GitHub Action 免裝重相依即可執行。
"""
```

- [ ] **Step 2: 寫失敗測試（roles）**

於 `tests/test_daily_status.py` 開頭：

```python
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
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: FAIL（`ModuleNotFoundError: polaris.daily_status.roles`）

- [ ] **Step 4: 實作 `roles.py`**

```python
"""username → 角色 對照表（唯一事實來源）。

username 取自 memory（2026-06-01 已用 GitHub API 驗證真實存在）；
Task 10 動工前會再驗一次。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Role:
    code: str  # "R1".."R7"
    name: str  # 中文姓名


# 鍵一律小寫；插入順序即 R1..R7。
_BY_USERNAME: dict[str, Role] = {
    "hbb97tw-netizen": Role("R1", "郝家銘"),
    "wayneshc": Role("R2", "施惠棋"),
    "officehsieh-afk": Role("R3", "謝劼恩"),
    "holajennytw": Role("R4", "吳瑾瑜"),
    "arronyang0416": Role("R5", "楊宗勲"),
    "aa851115tw-tech": Role("R6", "黃俊維"),
    "angelali2026888-blip": Role("R7", "李靜雲"),
}

ROLES: list[Role] = list(_BY_USERNAME.values())  # 已依 R1..R7 排序


def role_for(username: str) -> Role | None:
    return _BY_USERNAME.get(username.lower())
```

- [ ] **Step 5: 跑測試確認通過**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
git add src/polaris/daily_status/__init__.py src/polaris/daily_status/roles.py tests/test_daily_status.py
git commit -m "feat(daily-status): 角色對照表 roles.py"
```

---

### Task 2: timewindow.py（台北昨日 → UTC 區間）

**Files:**
- Create: `src/polaris/daily_status/timewindow.py`
- Test: `tests/test_daily_status.py`（追加）

- [ ] **Step 1: 寫失敗測試**

追加到 `tests/test_daily_status.py`：

```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: FAIL（`No module named ...timewindow`）

- [ ] **Step 3: 實作 `timewindow.py`**

```python
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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/polaris/daily_status/timewindow.py tests/test_daily_status.py
git commit -m "feat(daily-status): 台北昨日→UTC 時間窗 timewindow.py"
```

---

### Task 3: fetch.py（GitHubClient + Event + fetch_events）

**Files:**
- Create: `src/polaris/daily_status/fetch.py`
- Test: `tests/test_daily_status.py`（追加 FakeClient + happy path）

- [ ] **Step 1: 寫失敗測試（用假 client，不打網路）**

追加：

```python
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
```

> 註：FakeClient route key 用 `+`（search query 經 `urllib.parse.quote` 後空白會變 `%20`，但 `is:pr+is:merged` 這種片段以 `+` 連接的子字串需與實作組 query 的方式一致）。實作 `fetch_events` 組 query 時，請用 `+` 連接 qualifier（GitHub search 接受 `+` 當空白），子字串即可被 FakeClient 命中。

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: FAIL（`No module named ...fetch`）

- [ ] **Step 3: 實作 `fetch.py`**

```python
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
        events.append(Event("pr_merged", it["user"]["login"], it["number"], it["title"]))
    for it in _search(client, f"repo:{repo}+is:pr+created:{rng}"):
        events.append(Event("pr_opened", it["user"]["login"], it["number"], it["title"]))
    for it in _search(client, f"repo:{repo}+is:issue+is:closed+closed:{rng}"):
        events.append(Event("issue_closed", it["user"]["login"], it["number"], it["title"]))

    commits = client.get(f"{API}/repos/{repo}/commits?since={start}&until={end}&per_page=100")
    for c in commits if isinstance(commits, list) else []:
        login = (c.get("author") or {}).get("login")
        if login:
            events.append(Event("commit", login, None, ""))

    for pr in _search(client, f"repo:{repo}+is:pr+updated:{rng}"):
        num = pr["number"]
        reviews = client.get(f"{API}/repos/{repo}/pulls/{num}/reviews?per_page=100")
        for r in reviews if isinstance(reviews, list) else []:
            submitted, login = r.get("submitted_at"), (r.get("user") or {}).get("login")
            if submitted and login and start_utc <= _parse_iso(submitted) < end_utc:
                events.append(Event("review", login, num, pr["title"]))

    return events
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/polaris/daily_status/fetch.py tests/test_daily_status.py
git commit -m "feat(daily-status): GitHub 活動抓取 fetch.py"
```

---

### Task 4: aggregate.py（events → 每角色統計）

**Files:**
- Create: `src/polaris/daily_status/aggregate.py`
- Test: `tests/test_daily_status.py`（追加）

- [ ] **Step 1: 寫失敗測試**

追加：

```python
from polaris.daily_status import aggregate as AG
from polaris.daily_status.fetch import Event


def test_aggregate_groups_by_role_and_counts():
    events = [
        Event("pr_merged", "WayneSHC", 42, "merge X"),
        Event("commit", "WayneSHC", None, ""),
        Event("commit", "WayneSHC", None, ""),
        Event("review", "WayneSHC", 50, "rev"),
        Event("pr_opened", "holajennytw", 44, "wip Y"),
        Event("issue_closed", "officehsieh-afk", 7, "close Z"),
    ]
    digest = AG.aggregate(events, "2026-06-02")

    assert digest.date_str == "2026-06-02"
    r2 = digest.per_role["R2"]
    assert r2.merged_prs == [(42, "merge X")]
    assert r2.commits == 2
    assert r2.reviews == 1
    assert digest.per_role["R4"].opened_prs == [(44, "wip Y")]
    assert digest.per_role["R3"].closed_issues == [(7, "close Z")]
    # 所有 7 角色都在（含零活動）
    assert list(digest.per_role.keys()) == ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]


def test_aggregate_unmapped_author_collected_not_dropped():
    digest = AG.aggregate([Event("commit", "dependabot[bot]", None, "")], "2026-06-02")
    assert digest.unmapped == {"dependabot[bot]": 1}


def test_aggregate_has_activity_helper():
    empty = AG.aggregate([], "2026-06-02")
    assert AG.has_activity(empty) is False
    one = AG.aggregate([Event("commit", "WayneSHC", None, "")], "2026-06-02")
    assert AG.has_activity(one) is True
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: FAIL

- [ ] **Step 3: 實作 `aggregate.py`**

```python
"""把 Event 清單依 author→角色 分組統計成 DailyDigest（純函式）。"""
from __future__ import annotations

from dataclasses import dataclass, field

from .fetch import Event
from .roles import ROLES, Role, role_for


@dataclass
class RoleStat:
    role: Role
    merged_prs: list[tuple[int, str]] = field(default_factory=list)
    opened_prs: list[tuple[int, str]] = field(default_factory=list)
    reviews: int = 0
    closed_issues: list[tuple[int, str]] = field(default_factory=list)
    commits: int = 0


@dataclass
class DailyDigest:
    date_str: str  # 報告的台北日期 "YYYY-MM-DD"
    per_role: dict[str, RoleStat]  # 鍵為角色 code，序為 R1..R7
    unmapped: dict[str, int]  # login -> 事件數（未對應角色，不丟棄）


def aggregate(events: list[Event], date_str: str) -> DailyDigest:
    per_role = {r.code: RoleStat(role=r) for r in ROLES}
    unmapped: dict[str, int] = {}
    for e in events:
        role = role_for(e.author)
        if role is None:
            unmapped[e.author] = unmapped.get(e.author, 0) + 1
            continue
        st = per_role[role.code]
        if e.kind == "pr_merged":
            st.merged_prs.append((e.number, e.title))
        elif e.kind == "pr_opened":
            st.opened_prs.append((e.number, e.title))
        elif e.kind == "review":
            st.reviews += 1
        elif e.kind == "issue_closed":
            st.closed_issues.append((e.number, e.title))
        elif e.kind == "commit":
            st.commits += 1
    return DailyDigest(date_str=date_str, per_role=per_role, unmapped=unmapped)


def has_activity(digest: DailyDigest) -> bool:
    if digest.unmapped:
        return True
    for st in digest.per_role.values():
        if st.merged_prs or st.opened_prs or st.closed_issues or st.reviews or st.commits:
            return True
    return False
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/polaris/daily_status/aggregate.py tests/test_daily_status.py
git commit -m "feat(daily-status): 角色統計 aggregate.py"
```

---

### Task 5: render.py（CSV + 每日 block + 滾動 body 合併）

**Files:**
- Create: `src/polaris/daily_status/render.py`
- Test: `tests/test_daily_status.py`（追加）

- [ ] **Step 1: 寫失敗測試**

追加：

```python
from polaris.daily_status import render as RD


def _sample_digest():
    from polaris.daily_status.aggregate import aggregate
    from polaris.daily_status.fetch import Event

    return aggregate(
        [
            Event("pr_merged", "WayneSHC", 42, "merge X"),
            Event("commit", "WayneSHC", None, ""),
            Event("pr_opened", "holajennytw", 44, "wip Y"),
            Event("commit", "dependabot[bot]", None, ""),
        ],
        "2026-06-02",
    )


def test_render_csv_header_and_rows():
    csv_text = RD.render_csv(_sample_digest())
    lines = csv_text.strip().splitlines()
    assert lines[0] == "日期,角色,成員,完成PR,進行中PR,Review數,關閉Issue,commit數,摘要"
    assert len(lines) == 1 + 7  # header + 7 角色
    assert lines[1].startswith("2026-06-02,R1,郝家銘,")
    assert "2026-06-02,R2,施惠棋,1,0,0,0,1," in csv_text


def test_render_day_block_has_markers_and_unmapped():
    block = RD.render_day_block(_sample_digest())
    assert block.startswith("<!--day:2026-06-02-->")
    assert block.rstrip().endswith("<!--/day:2026-06-02-->")
    assert "<details>" in block and "dependabot[bot]×1" in block


def test_render_day_block_no_activity_note():
    from polaris.daily_status.aggregate import aggregate

    block = RD.render_day_block(aggregate([], "2026-06-02"))
    assert "今日無 GitHub 活動" in block


def test_merge_rolling_body_prepend_dedup_trim():
    d1 = RD.render_day_block_for_test("2026-06-01")  # helper 見下
    d2 = RD.render_day_block_for_test("2026-06-02")
    body = RD.merge_rolling_body("", d1, "2026-06-01")
    body = RD.merge_rolling_body(body, d2, "2026-06-02")
    # 最新在上
    assert body.index("day:2026-06-02") < body.index("day:2026-06-01")
    # 同日重跑 → 不重複
    body2 = RD.merge_rolling_body(body, d2, "2026-06-02")
    assert body2.count("<!--day:2026-06-02-->") == 1
    # 超過 keep_days 會修剪
    trimmed = body
    for i in range(3, 20):
        blk = RD.render_day_block_for_test(f"2026-06-{i:02d}")
        trimmed = RD.merge_rolling_body(trimmed, blk, f"2026-06-{i:02d}", keep_days=14)
    assert trimmed.count("<!--day:") == 14
    assert "reports/daily" in trimmed  # footer 指向 status 分支
```

> `render_day_block_for_test(date_str)` 是測試輔助，請在 `render.py` 提供：回傳僅含 marker 的最小 block，方便測 merge 行為。

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: FAIL

- [ ] **Step 3: 實作 `render.py`**

```python
"""把 DailyDigest 轉成 CSV / 每日 Markdown block，並合併滾動 Issue body（純函式）。"""
from __future__ import annotations

import csv
import io
import re

from .aggregate import DailyDigest, has_activity

CSV_HEADER = [
    "日期", "角色", "成員", "完成PR", "進行中PR", "Review數", "關閉Issue", "commit數", "摘要",
]

_HEADER = "# 📊 Polaris Desk — Daily Status\n_自動產生，僅涵蓋 GitHub 活動（PR/commit/review/issue）。_"
_FOOTER = "---\n_更早的每日紀錄見 `status` 分支 `reports/daily/`。_"
_DAY_RE = re.compile(r"<!--day:(\d{4}-\d{2}-\d{2})-->.*?<!--/day:\1-->", re.DOTALL)


def render_csv(digest: DailyDigest) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADER)
    for code, st in digest.per_role.items():
        bits = []
        if st.merged_prs:
            bits.append("合併 " + ",".join(f"#{n}" for n, _ in st.merged_prs))
        if st.opened_prs:
            bits.append("開 " + ",".join(f"#{n}" for n, _ in st.opened_prs))
        if st.reviews:
            bits.append(f"review {st.reviews}")
        if st.closed_issues:
            bits.append("關 " + ",".join(f"#{n}" for n, _ in st.closed_issues))
        w.writerow([
            digest.date_str, code, st.role.name,
            len(st.merged_prs), len(st.opened_prs), st.reviews,
            len(st.closed_issues), st.commits, "；".join(bits),
        ])
    return buf.getvalue()


def render_day_block(digest: DailyDigest) -> str:
    d = digest.date_str
    lines = [
        f"<!--day:{d}-->",
        f"<details><summary>{d} (Asia/Taipei)</summary>",
        "",
        "| 角色 | 成員 | 完成PR | 進行中 | Review | 關閉Issue | commit |",
        "|---|---|---|---|---|---|---|",
    ]
    for code, st in digest.per_role.items():
        merged = ", ".join(f"#{n}" for n, _ in st.merged_prs) or "—"
        opened = ", ".join(f"#{n}" for n, _ in st.opened_prs) or "—"
        closed = ", ".join(f"#{n}" for n, _ in st.closed_issues) or "—"
        lines.append(
            f"| {code} | {st.role.name} | {merged} | {opened} | "
            f"{st.reviews or '—'} | {closed} | {st.commits or '—'} |"
        )
    if digest.unmapped:
        um = ", ".join(f"{u}×{c}" for u, c in sorted(digest.unmapped.items()))
        lines += ["", f"> ⚠️ 未對應帳號（請補 `roles.py`）：{um}"]
    if not has_activity(digest):
        lines += ["", "> 今日無 GitHub 活動"]
    lines += ["", "</details>", f"<!--/day:{d}-->"]
    return "\n".join(lines)


def render_day_block_for_test(date_str: str) -> str:
    """測試輔助：最小合法 day block。"""
    return f"<!--day:{date_str}-->\n<details><summary>{date_str}</summary>x</details>\n<!--/day:{date_str}-->"


def merge_rolling_body(
    existing_body: str, day_block: str, date_str: str, keep_days: int = 14
) -> str:
    blocks = {m.group(1): m.group(0) for m in _DAY_RE.finditer(existing_body)}
    blocks[date_str] = day_block.strip()  # 新增 / 取代今日（同日重跑 idempotent）
    ordered = sorted(blocks.items(), key=lambda kv: kv[0], reverse=True)[:keep_days]
    return "\n\n".join([_HEADER] + [b for _, b in ordered] + [_FOOTER])
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/polaris/daily_status/render.py tests/test_daily_status.py
git commit -m "feat(daily-status): CSV / 每日 block / 滾動 body 合併 render.py"
```

---

### Task 6: publish.py（找 / 更新 / 建立滾動 Issue）

**Files:**
- Create: `src/polaris/daily_status/publish.py`
- Test: `tests/test_daily_status.py`（追加）

- [ ] **Step 1: 寫失敗測試（用 Task 3 的 FakeClient）**

追加：

```python
from polaris.daily_status import publish as PB


def test_upsert_creates_issue_when_none_exists():
    client = FakeClient({"labels=daily-status": []})  # 找不到既有 issue
    num = PB.upsert_rolling_issue(client, "o/r", "daily-status", "📊 T", "BODY")
    assert num == 123
    assert client.posts and client.posts[0][1]["labels"] == ["daily-status"]
    assert client.posts[0][1]["title"] == "📊 T"
    assert client.posts[0][1]["body"] == "BODY"


def test_upsert_patches_existing_issue():
    client = FakeClient({"labels=daily-status": [{"number": 88, "body": "old"}]})
    num = PB.upsert_rolling_issue(client, "o/r", "daily-status", "📊 T", "NEW")
    assert num == 88
    assert client.patches and "/issues/88" in client.patches[0][0]
    assert client.patches[0][1]["body"] == "NEW"
    assert not client.posts  # 已存在就不新建


def test_find_rolling_issue_returns_first():
    client = FakeClient({"labels=daily-status": [{"number": 5, "body": "b"}]})
    issue = PB.find_rolling_issue(client, "o/r", "daily-status")
    assert issue["number"] == 5
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: FAIL

- [ ] **Step 3: 實作 `publish.py`**

```python
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
```

> 註：以不存在的 label 建 issue 時，GitHub 會自動建立該 label，故不需另外建 label。

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/polaris/daily_status/publish.py tests/test_daily_status.py
git commit -m "feat(daily-status): 滾動 Issue 維護 publish.py"
```

---

### Task 7: __main__.py（CLI 串接）

**Files:**
- Create: `src/polaris/daily_status/__main__.py`
- Test: `tests/test_daily_status.py`（追加 dry-run smoke）

- [ ] **Step 1: 寫失敗測試（dry-run，注入假 client + 固定日期，不打網路）**

追加：

```python
from polaris.daily_status import __main__ as M


def test_cli_dry_run_prints_block_and_csv(capsys, monkeypatch):
    # 注入假 client（回 0 活動）與固定「今天」
    monkeypatch.setattr(M, "GitHubClient", lambda token: FakeClient({}))
    monkeypatch.setattr(M, "_today_taipei", lambda: date(2026, 6, 3))
    rc = M.main(["--repo", "o/r", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "<!--day:2026-06-02-->" in out  # 報告昨日
    assert "日期,角色,成員" in out


def test_cli_writes_files_and_posts_issue(tmp_path, monkeypatch):
    fake = FakeClient({"labels=daily-status": []})
    monkeypatch.setattr(M, "GitHubClient", lambda token: fake)
    monkeypatch.setattr(M, "_today_taipei", lambda: date(2026, 6, 3))
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    rc = M.main(["--repo", "o/r", "--out-dir", str(tmp_path), "--post-issue"])
    assert rc == 0
    assert (tmp_path / "2026-06-02.md").exists()
    assert (tmp_path / "2026-06-02.csv").exists()
    assert fake.posts  # 有發 issue
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/bin/pytest tests/test_daily_status.py -q`
Expected: FAIL

- [ ] **Step 3: 實作 `__main__.py`**

```python
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
```

- [ ] **Step 4: 跑測試確認通過 + 全套測試 + lint**

Run: `.venv/bin/pytest tests/test_daily_status.py -q && .venv/bin/ruff check src/polaris/daily_status tests/test_daily_status.py`
Expected: PASS、ruff 全過

- [ ] **Step 5: Commit**

```bash
git add src/polaris/daily_status/__main__.py tests/test_daily_status.py
git commit -m "feat(daily-status): CLI 入口 __main__.py"
```

---

### Task 8: Makefile 兩個 target

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: 在 `.PHONY` 行尾加上兩個 target 名稱**

把：
```makefile
.PHONY: setup install dev db-up db-down test fmt lint check check-keys
```
改成：
```makefile
.PHONY: setup install dev db-up db-down test fmt lint check check-keys daily-status daily-status-dry
```

- [ ] **Step 2: 在 `check-keys` target 之後、`check:` 之前插入**

```makefile
daily-status:   ## 產生昨日各角色進度並更新滾動 Issue（需 GITHUB_TOKEN，本機可用 gh auth token）
	GITHUB_TOKEN=$${GITHUB_TOKEN:-$$(gh auth token)} PYTHONPATH=src .venv/bin/python -m polaris.daily_status --post-issue

daily-status-dry: ## 試跑：只印不發、不寫檔
	GITHUB_TOKEN=$${GITHUB_TOKEN:-$$(gh auth token)} PYTHONPATH=src .venv/bin/python -m polaris.daily_status --dry-run
```

- [ ] **Step 3: 驗證 dry-run 真的能跑（需本機已 `gh auth login`）**

Run: `make daily-status-dry`
Expected: 印出昨日的 `<!--day:...-->` block 與 CSV header（實際打 GitHub API，repo 預設 `WayneSHC/polaris-desk`）。若未登入 gh 會於 token 取得失敗 — 屬預期，登入後再試。

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "chore(daily-status): make daily-status / daily-status-dry"
```

---

### Task 9: GitHub Action 排程 workflow

**Files:**
- Create: `.github/workflows/daily-status.yml`

- [ ] **Step 1: 建 workflow 檔**

```yaml
name: daily-status

on:
  schedule:
    - cron: "10 23 * * *"   # 23:10 UTC = 07:10 Asia/Taipei（報告台北昨日）
  workflow_dispatch: {}      # 可手動觸發測試

permissions:
  contents: write            # 推 status 分支
  issues: write              # 更新/建立滾動 Issue

concurrency:
  group: daily-status
  cancel-in-progress: false

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: 產生進度 + 更新滾動 Issue
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          OUT_DIR: ${{ runner.temp }}/daily
        run: |
          PYTHONPATH=src python -m polaris.daily_status --out-dir "$OUT_DIR" --post-issue

      - name: 發佈到 status 分支
        env:
          OUT_DIR: ${{ runner.temp }}/daily
        run: |
          set -euo pipefail
          git config user.name "polaris-status-bot"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          if git ls-remote --exit-code --heads origin status >/dev/null 2>&1; then
            git fetch origin status:status   # 直接建本地 status，避開 checkout@v4 受限 refspec
            git switch status
          else
            git switch --orphan status
            git rm -rf . >/dev/null 2>&1 || true
          fi
          mkdir -p reports/daily
          cp "$OUT_DIR"/* reports/daily/
          git add reports/daily
          git commit -m "chore(status): daily $(date -u +%F)" || { echo "no changes"; exit 0; }
          git push origin status
```

- [ ] **Step 2: 本地 YAML 語法檢查**

Run: `.venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/daily-status.yml')); print('yaml ok')"`
Expected: `yaml ok`（若無 pyyaml，可改用 `python -c "import json"` 跳過；GitHub 會在 push 後驗證）

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/daily-status.yml
git commit -m "ci(daily-status): 每日排程 workflow + status 分支發佈"
```

---

### Task 10: 動工前驗證 + 整體驗收（含對外動作，需 PM 點頭）

**Files:** 無（驗證為主）

- [ ] **Step 1: 驗 7 個 GitHub username 真實存在**

Run:
```bash
for u in hbb97tw-netizen WayneSHC officehsieh-afk holajennytw Arronyang0416 aa851115tw-tech angelali2026888-blip; do
  echo -n "$u -> "; gh api "users/$u" --jq .login 2>/dev/null || echo "❌ 不存在（需更新 roles.py）"
done
```
Expected: 7 個都印出對應 login。若有 ❌，更新 `roles.py` 的鍵並補測試後重跑 Task 1。

- [ ] **Step 2: 全套測試 + lint + 確認沒裝到新相依**

Run: `make check`
Expected: ruff 全過、所有測試 pass（含既有 70+ 題）。

- [ ] **Step 3: 本機端到端 dry-run（實打 API）**

Run: `make daily-status-dry`
Expected: 印出昨日真實活動的 block 與 CSV，未對應帳號（若有）顯示在區塊內。

- [ ] **Step 4:〔對外，需 PM 確認〕推分支 + 開 PR**

```bash
git push -u origin feat/daily-status-sync
gh pr create --base main --head feat/daily-status-sync \
  --title "feat: 每日 GitHub 活動 → 各角色進度（Issue + Notion CSV）" \
  --body "見 docs/superpowers/specs/2026-06-03-daily-status-sync-design.md。需 1 approval。"
```

- [ ] **Step 5:〔對外，需 PM 確認〕手動觸發 Action 驗收一次**

PR 併入 main 後（workflow 需在預設分支才會出現於 Actions 排程，但 `workflow_dispatch` 可在分支上手動跑）：
```bash
gh workflow run daily-status.yml --ref main
gh run watch
```
Expected: run 綠燈；產生/更新「📊 Daily Status (rolling)」Issue；`status` 分支出現 `reports/daily/<昨日>.md` 與 `.csv`。
驗收：開 Issue 看摘要正確、下載 status 分支 CSV 試匯入 Notion 一次。

---

## 完成定義（DoD）

- `src/polaris/daily_status/` 六模組 + CLI 完成，單元測試全綠、ruff 全過、未新增第三方相依。
- `make daily-status-dry` 本機可印出昨日各角色進度。
- workflow 手動觸發成功：滾動 Issue 更新、`status` 分支有當日 md+csv。
- PM 確認可從 status 分支 CSV 匯入 Notion。
- PR 經 1 approval 併入 `main`。
