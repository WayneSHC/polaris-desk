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
