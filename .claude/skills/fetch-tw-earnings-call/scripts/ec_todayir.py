"""TodayIR IR 站 adapter（中信金等）。

法說會簡報頁 `/c/financial_analyst?year=<西元>` 每年一頁，PDF 連結由 JS 注入，
形如 `https://media-ctbc.todayir.com/<id>_tc.pdf' ...>2026 第一季 法說會簡報</a>`。
語言由檔名後綴判定：_tc/_ch → zh、_en/_eng → en（預設 zh）。
event_date 此來源頁不含，留給編排層以 PDF 首頁補（date_source 之後標記）。
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from ec_model import Doc, cn_quarter_num, to_period

_LINK = re.compile(
    r"(https?://[^'\"]*todayir\.com/[^'\"]+\.pdf)'[^>]*>\s*"
    r"(\d{4})\s*第([一二三四])季\s*([^<]*)</a>"
)


def supports(stock_id: str, registry: dict | None) -> bool:
    return bool(registry) and registry.get("vendor") == "todayir"


def _lang_of(url: str) -> str:
    low = url.lower()
    if any(t in low for t in ("_en", "_eng", "-en", "eng.pdf")):
        return "en"
    return "zh"


def _doc_type_of(label: str) -> str:
    return "transcript" if ("逐字" in label or "transcript" in label.lower()) else "presentation"


def fetch(
    stock_id: str,
    years: Iterable[int],
    http_get: Callable[[str], bytes],
    registry: dict,
) -> list[Doc]:
    company = registry["name"]
    tmpl = registry["page_tmpl"]
    seen: set[str] = set()
    out: list[Doc] = []
    for y in years:
        page = tmpl.format(year=y)
        html = http_get(page).decode("utf-8", "replace")
        for url, yr, q_cn, label in _LINK.findall(html):
            if url in seen:
                continue
            seen.add(url)
            out.append(Doc(
                stock_id=stock_id,
                company=company,
                doc_type=_doc_type_of(label),
                fiscal_period=to_period(int(yr), cn_quarter_num(q_cn)),
                lang=_lang_of(url),
                event_date="",
                date_source="unknown",
                source_url=url,
                source_page=page,
            ))
    return out
