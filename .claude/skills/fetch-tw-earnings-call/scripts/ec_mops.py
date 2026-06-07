"""MOPS 法人說明會一覽表（集中式底層，任意股票代號可用）。

公開資訊觀測站改版為 SPA，但舊版 AJAX 端點仍可用且接受 GET：
  GET https://mopsov.twse.com.tw/mops/web/ajax_t100sb02_1?...&co_id=<ticker>&year=<民國年>
回 HTML 表格，每列含中文(M)/英文(E)簡報檔名；PDF 在 nas/STR/<檔名>。
- 只回 presentation（MOPS 無逐字稿）。
- period 取自主旨「NNN年度第X季」；event_date 取自檔名 8 碼日期。
- 投資人會議重用同份簡報 → 依檔名去重，保留能解析出季別的那筆。
"""
from __future__ import annotations

import html as _html
import re
from collections.abc import Callable, Iterable
from urllib.parse import urlencode

from ec_model import Doc, to_period

ENDPOINT = "https://mopsov.twse.com.tw/mops/web/ajax_t100sb02_1"
PDF_BASE = "https://mopsov.twse.com.tw/nas/STR/"
_TR = re.compile(r"<tr[^>]*>.*?</tr>", re.S | re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")
_SUBJ_Q = re.compile(r"(\d{2,3})\s*年(?:度)?\s*第\s*([一二三四1-4])\s*季")
_CN_Q = {"一": 1, "二": 2, "三": 3, "四": 4, "1": 1, "2": 2, "3": 3, "4": 4}


def _query(stock_id: str, roc_year: int) -> str:
    return ENDPOINT + "?" + urlencode({
        "encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1,
        "TYPEK": "all", "co_id": stock_id, "year": roc_year,
    })


def _cell_text(fragment: str) -> str:
    return _html.unescape(_TAG.sub("", fragment)).strip()


def _period_from_subject(subject: str) -> str:
    m = _SUBJ_Q.search(subject)
    return to_period(1911 + int(m.group(1)), _CN_Q[m.group(2)]) if m else ""


def _parse(html_text: str, stock_id: str) -> list[Doc]:
    file_re = re.compile(rf"({re.escape(stock_id)})(\d{{8}})([ME])(\d{{3}})\.pdf")
    best: dict[str, Doc] = {}  # filename -> Doc（優先保留能解析季別者）
    for row in _TR.findall(html_text):
        cells = [t for t in (_cell_text(c) for c in _TD.findall(row)) if t]
        company = cells[1] if len(cells) > 1 else ""
        subject = next((c for c in cells if "季" in c or "概況" in c or "說明會" in c), "")
        period = _period_from_subject(subject)
        for m in file_re.finditer(row):
            fname, ymd, flag = m.group(0), m.group(2), m.group(3)
            doc = Doc(
                stock_id=stock_id, company=company, doc_type="presentation",
                fiscal_period=period, lang="zh" if flag == "M" else "en",
                event_date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}",
                date_source="source_listing",
                source_url=PDF_BASE + fname, source_page=ENDPOINT,
            )
            prev = best.get(fname)
            if prev is None or (not prev.fiscal_period and period):
                best[fname] = doc
    return [d for d in best.values() if d.fiscal_period]


def fetch(stock_id: str, years: Iterable[int], http_get: Callable[[str], bytes]) -> list[Doc]:
    out: list[Doc] = []
    for y in years:
        html_text = http_get(_query(stock_id, y - 1911)).decode("utf-8", "replace")
        out.extend(_parse(html_text, stock_id))
    return out
