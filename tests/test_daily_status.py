"""Daily Status Sync 單元測試（roles / timewindow / aggregate / render / publish / fetch）。"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from polaris.daily_status import __main__ as M
from polaris.daily_status import aggregate as AG
from polaris.daily_status import fetch as F
from polaris.daily_status import publish as PB
from polaris.daily_status import render as RD
from polaris.daily_status import roles as R
from polaris.daily_status import timewindow as TW
from polaris.daily_status.fetch import Event


# ── Task 1: roles ──────────────────────────────────────────────────────────────

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


# ── Task 2: timewindow ─────────────────────────────────────────────────────────

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


# ── Task 3: fetch ──────────────────────────────────────────────────────────────

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
        "is:pr+is:open+created": {"items": [{"user": {"login": "holajennytw"}, "number": 44, "title": "wip Y"}]},
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


def test_fetch_opened_pr_query_uses_is_open():
    """opened-PR search query must include is:open so merged PRs are excluded."""
    client = FakeClient({})
    start = datetime(2026, 6, 1, 16, 0, tzinfo=ZoneInfo("UTC"))
    end = datetime(2026, 6, 2, 16, 0, tzinfo=ZoneInfo("UTC"))
    F.fetch_events(client, "WayneSHC/polaris-desk", start, end)
    assert any("is:open" in g for g in client.gets), (
        "opened-PR search must include is:open in the query URL"
    )


def test_fetch_skips_null_user():
    """A search result with user=None must be skipped rather than raising TypeError."""
    routes = {
        "is:pr+is:merged": {"items": [{"user": None, "number": 99, "title": "ghost PR"}]},
        "is:pr+is:open+created": {"items": []},
        "is:issue+is:closed": {"items": []},
        "/commits": [],
        "is:pr+updated": {"items": []},
    }
    client = FakeClient(routes)
    start = datetime(2026, 6, 1, 16, 0, tzinfo=ZoneInfo("UTC"))
    end = datetime(2026, 6, 2, 16, 0, tzinfo=ZoneInfo("UTC"))
    events = F.fetch_events(client, "WayneSHC/polaris-desk", start, end)
    # The null-user item must be silently dropped, not crash
    assert all(e.kind != "pr_merged" for e in events)


# ── Task 4: aggregate ──────────────────────────────────────────────────────────

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


# ── Task 5: render ─────────────────────────────────────────────────────────────

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


# ── Task 6: publish ────────────────────────────────────────────────────────────

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


# ── Task 7: __main__ ───────────────────────────────────────────────────────────

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


def test_cli_updates_existing_issue(tmp_path, monkeypatch):
    """When a rolling issue already exists, main() must PATCH (not POST) it,
    and the patched body must contain both the old day block and the new one."""
    old_body = (
        "<!--day:2026-06-01-->\n"
        "<details><summary>2026-06-01</summary>x</details>\n"
        "<!--/day:2026-06-01-->"
    )
    existing_issue = [{"number": 88, "body": old_body}]
    fake = FakeClient({"labels=daily-status": existing_issue})
    monkeypatch.setattr(M, "GitHubClient", lambda token: fake)
    # _today_taipei → 2026-06-03, so date_str = 2026-06-02
    monkeypatch.setattr(M, "_today_taipei", lambda: date(2026, 6, 3))
    monkeypatch.setenv("GITHUB_TOKEN", "x")

    rc = M.main(["--repo", "o/r", "--out-dir", str(tmp_path), "--post-issue"])
    assert rc == 0

    # Must have PATCHed the existing issue, not created a new one
    assert fake.patches, "expected patch call for existing issue"
    assert not fake.posts, "expected no new issue to be created"

    # The patched body must contain both the old 2026-06-01 block and the new 2026-06-02 block
    patched_body = fake.patches[0][1]["body"]
    assert "<!--day:2026-06-01-->" in patched_body, "old day block must be preserved"
    assert "<!--day:2026-06-02-->" in patched_body, "new day block must be present"
