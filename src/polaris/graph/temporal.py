"""Temporal Anchoring（R2 W2 D6 / FR-007）— 解析問題中的期間語句。

把「最近兩季 / 2024 全年 / 2024Q3 / 2024年第三季」解析成具體季別清單
（"2024Q3" 格式，對齊 :mod:`polaris.vectorstore.base` 的 period 慣例），
讓 retriever 能「只取對應期間資料」。

純函式、無 LLM、無 ``datetime.now()``（相對期間用可注入的 ``anchor`` 解析，
確保確定性可測）。預設 anchor 為佔位值；W2 接 R4 後改為「DB 最新可用季別」。
"""
from __future__ import annotations

import re

from polaris.graph.state import PeriodSpec

#: 相對期間（最近 N 季）的解析基準。佔位值，待 R4 提供 DB 最新季別後動態帶入。
DEFAULT_ANCHOR = "2025Q1"

_CN_NUM = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4}

# 優先序：季別（含 Q 與「第n季」）> 相對 > 全年。先比對更具體的樣式。
_RE_QUARTER_Q = re.compile(r"(\d{4})\s*[Qq]\s*([1-4])")
_RE_QUARTER_CN = re.compile(r"(\d{4})\s*年?\s*第\s*([一二三四1-4])\s*季")
_RE_RECENT = re.compile(r"(?:最近|近)\s*([一二兩三四\d]+)\s*季")
_RE_FISCAL_YEAR = re.compile(r"(\d{4})\s*(?:全年|年度|年)")


def _to_int(token: str) -> int:
    return int(token) if token.isdigit() else _CN_NUM.get(token, 0)


def _qtuple(q: str) -> tuple[int, int]:
    return int(q[:4]), int(q[5])


def _fmt(year: int, quarter: int) -> str:
    return f"{year}Q{quarter}"


def _prev(year: int, quarter: int) -> tuple[int, int]:
    return (year - 1, 4) if quarter == 1 else (year, quarter - 1)


def _recent(anchor: str, n: int) -> list[str]:
    year, quarter = _qtuple(anchor)
    out: list[str] = []
    for _ in range(max(0, n)):
        out.append(_fmt(year, quarter))
        year, quarter = _prev(year, quarter)
    return out


def _fiscal_year(year: int) -> list[str]:
    return [_fmt(year, q) for q in (1, 2, 3, 4)]


def parse_period(query: str, *, anchor: str = DEFAULT_ANCHOR) -> PeriodSpec:
    """解析期間語句 → PeriodSpec。比對不到回 kind='none'。"""
    text = query or ""

    m = _RE_QUARTER_Q.search(text)
    if m:
        q = f"{m.group(1)}Q{m.group(2)}"
        return PeriodSpec(hint=m.group(0).strip(), kind="quarter", quarters=[q])

    m = _RE_QUARTER_CN.search(text)
    if m:
        q = _fmt(int(m.group(1)), _to_int(m.group(2)))
        return PeriodSpec(hint=m.group(0).strip(), kind="quarter", quarters=[q])

    m = _RE_RECENT.search(text)
    if m:
        n = _to_int(m.group(1))
        if n > 0:
            return PeriodSpec(
                hint=m.group(0).strip(),
                kind="recent_quarters",
                quarters=_recent(anchor, n),
            )

    m = _RE_FISCAL_YEAR.search(text)
    if m:
        return PeriodSpec(
            hint=m.group(0).strip(),
            kind="fiscal_year",
            quarters=_fiscal_year(int(m.group(1))),
        )

    return PeriodSpec(hint="", kind="none", quarters=[])


__all__ = ["parse_period", "DEFAULT_ANCHOR"]
