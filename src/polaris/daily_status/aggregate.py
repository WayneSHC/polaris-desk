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
