"""法說會下載：值物件 + 期別/日期正規化 + 檔名產生（純函式、無 I/O）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

LANG_FLAG = {"zh": "M", "en": "E"}  # M=中文 E=英文（使用者指定）
_MONTH_Q = {"03": 1, "06": 2, "09": 3, "12": 4}
_CN_Q = {"一": 1, "二": 2, "三": 3, "四": 4}
_ROC_DATE = re.compile(r"(?:民國)?\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_WEST_DATE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


@dataclass(frozen=True)
class Doc:
    stock_id: str
    company: str
    doc_type: str        # "presentation" | "transcript"
    fiscal_period: str   # "2026Q1"
    lang: str            # "zh" | "en"
    event_date: str      # ISO "2026-05-19" or "" if unknown
    date_source: str     # "pdf_first_page" | "source_listing" | "unknown"
    source_url: str
    source_page: str


def month_to_quarter(mm: str) -> int:
    return _MONTH_Q[mm.zfill(2)]


def cn_quarter_num(cn: str) -> int:
    return _CN_Q[cn]


def to_period(year: int, quarter: int) -> str:
    return f"{year}Q{quarter}"


def parse_roc_date(text: str) -> str:
    """從一段文字抽法說會日期 → ISO。先試西元（4 碼年），再試民國（2-3 碼年）。"""
    m = _WEST_DATE.search(text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    m = _ROC_DATE.search(text)
    if m:
        y, mo, d = 1911 + int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return ""


def build_filename(d: Doc, seq: int, ext: str = "pdf") -> str:
    date_token = d.event_date.replace("-", "") if d.event_date else "00000000"
    flag = LANG_FLAG[d.lang]
    return (
        f"{d.stock_id}_{date_token}{flag}{seq:03d}_"
        f"{d.fiscal_period}_concall_{d.doc_type}.{ext}"
    )
