# fetch-tw-earnings-call Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `fetch-tw-earnings-call` skill that downloads Taiwan-listed companies' earnings-call (法說會) presentations and transcripts (中/英) for any stock id, bypassing MOPS anti-crawling by hitting authoritative sources directly.

**Architecture:** Hybrid source resolution — a per-vendor adapter (TodayIR first, richer: zh+en presentation + transcript when published) plus a centralized MOPS 法人說明會一覽表 base that works for any stock id. Results merge by `(fiscal_period, doc_type, lang)` and dedupe by content md5. All skill scripts are stdlib-only and self-contained so the skill can be copied to `~/.claude/skills/` and run in any project. Network access is dependency-injected (`http_get`) so unit tests run against saved HTML fixtures with zero network.

**Tech Stack:** Python 3.13 (stdlib: `urllib`, `re`, `hashlib`, `json`, `subprocess`, `dataclasses`), `pdftotext` (poppler, already installed) for event-date extraction, pytest, ruff (line-length 100).

---

## File Structure

```
.claude/skills/fetch-tw-earnings-call/
├─ SKILL.md                       # trigger + usage doc
└─ scripts/
   ├─ fetch_earnings_call.py      # CLI entry: resolve → merge → dedupe → download → manifest
   ├─ ec_model.py                 # Doc dataclass, period/date helpers, filename builder
   ├─ ec_companies.py             # stock_id → {name, vendor, page_tmpl} registry
   ├─ ec_todayir.py               # TodayIR adapter (supports/fetch)
   └─ ec_mops.py                  # MOPS 法人說明會一覽表 base source
tests/
├─ conftest.py                    # adds skill scripts dir to sys.path (append if exists)
├─ fixtures/ctbc_financial_analyst_2026.html   # saved TodayIR page (fixture)
├─ fixtures/mops_t100sb02_2891.<ext>           # saved MOPS response (captured in Task 6)
├─ test_ec_model.py
├─ test_ec_todayir.py
└─ test_ec_mops.py
```

Module responsibilities (each independently testable):
- `ec_model` — pure value logic: normalize period, parse ROC date string, build filename. No I/O.
- `ec_companies` — static dict + `lookup(stock_id)`. No I/O.
- `ec_todayir` — `supports(stock_id, registry)`, `fetch(stock_id, years, http_get, registry) -> list[Doc]`. I/O via injected `http_get`.
- `ec_mops` — `fetch(stock_id, years, http_get) -> list[Doc]`. I/O via injected `http_get`.
- `fetch_earnings_call` — orchestration: `merge_dedupe(docs, blobs)`, download loop, manifest writer, `main()`.

Adapter convention (duck-typed, no ABC needed): a source module exposes `fetch(stock_id, years, http_get, ...) -> list[Doc]`; an adapter additionally exposes `supports(stock_id, registry) -> bool`.

---

## Task 1: Scaffold skill dir, SKILL.md, and conftest path wiring

**Files:**
- Create: `.claude/skills/fetch-tw-earnings-call/SKILL.md`
- Create: `.claude/skills/fetch-tw-earnings-call/scripts/__init__.py` (empty — marks dir, not imported as package)
- Create: `tests/conftest.py`

- [ ] **Step 1: Create SKILL.md**

```markdown
---
name: fetch-tw-earnings-call
description: Download Taiwan-listed companies' earnings-call (法說會) presentations and transcripts (Chinese + English) by stock id. Use when the user wants to fetch 法說會/法人說明會 簡報 or 逐字稿 for a TWSE/TPEx ticker (e.g. 2891 中信金, 2330 台積電), or mentions 公開資訊觀測站/MOPS being blocked for crawling. Bypasses MOPS anti-crawling by hitting authoritative IR sources directly.
---

# Fetch Taiwan Earnings-Call Materials

Downloads 法說會 (investor conference) **presentations** and **transcripts** for a given
stock id, Chinese and English, into `data/<stock_id>_<name>/` with a `manifest.json`
that carries source provenance (引用接地, R4).

## Why not MOPS scraping
公開資訊觀測站 (MOPS) blocks aggressive crawling. This skill instead hits **authoritative
sources**: the company's IR site via a per-vendor adapter (richer — zh+en + transcript when
published) plus the MOPS 法人說明會一覽表 as a generic base that works for any stock id.
Results merge and dedupe by content md5.

## Usage
```bash
python .claude/skills/fetch-tw-earnings-call/scripts/fetch_earnings_call.py \
    --stock-id 2891 --from 2021 --to 2026
# output: data/2891_中信金控/<files>.pdf + manifest.json
```

Options: `--stock-id` (required), `--from`/`--to` (year range, default 2021..current),
`--out` (default `data/<stock_id>_<name>`).

## Output naming
`<ticker>_<yyyymmdd><L><nnn>_<period>_concall_<doctype>.pdf`
- `yyyymmdd` = 法說會 held date (from PDF first page; falls back to source listing date)
- `L` = `M` (中文) / `E` (英文); `nnn` = per (ticker, date, lang) sequence from 001
- `period` = `YYYYQn`; `doctype` = `presentation` | `transcript`
- e.g. `2891_20260519M001_2026Q1_concall_presentation.pdf`

## Coverage
Companies in the registry (`ec_companies.py`) with a vendor adapter get zh+en + transcript.
Other stock ids fall back to the MOPS base (presentation only). To add a company, extend the
registry and (if a new IR vendor) add an adapter under `scripts/`.

## Notes
- Most TW companies do **not** publish transcripts; the skill fetches them only when present
  and notes their absence in the run summary. It never fabricates a manifest entry.
- This skill only downloads + writes a manifest. Parsing/chunking/embedding is R4 ingestion.
```

- [ ] **Step 2: Create the empty package marker**

```bash
mkdir -p .claude/skills/fetch-tw-earnings-call/scripts
: > .claude/skills/fetch-tw-earnings-call/scripts/__init__.py
```

- [ ] **Step 3: Create tests/conftest.py to make skill modules importable**

```python
"""讓 tests 能 import skill 的 stdlib-only 模組（不進 polaris 套件、保持可攜）。"""
from __future__ import annotations

import sys
from pathlib import Path

_SKILL_SCRIPTS = (
    Path(__file__).resolve().parent.parent
    / ".claude" / "skills" / "fetch-tw-earnings-call" / "scripts"
)
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))
```

> If `tests/conftest.py` already exists, append the `_SKILL_SCRIPTS` block instead of overwriting.

- [ ] **Step 4: Verify pytest still collects cleanly**

Run: `uv run pytest -q`
Expected: existing tests pass; no import/collection errors from the new conftest.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/fetch-tw-earnings-call tests/conftest.py
git commit -m "feat(skill): scaffold fetch-tw-earnings-call (SKILL.md + path wiring)"
```

---

## Task 2: `ec_model` — period helpers and filename builder

**Files:**
- Create: `.claude/skills/fetch-tw-earnings-call/scripts/ec_model.py`
- Test: `tests/test_ec_model.py`

- [ ] **Step 1: Write the failing tests**

```python
"""ec_model 純函式：期別正規化、ROC 日期解析、檔名產生。"""
from __future__ import annotations

from ec_model import Doc, build_filename, cn_quarter_num, month_to_quarter, parse_roc_date, to_period


def test_month_to_quarter():
    assert month_to_quarter("03") == 1
    assert month_to_quarter("06") == 2
    assert month_to_quarter("09") == 3
    assert month_to_quarter("12") == 4


def test_cn_quarter_num():
    assert cn_quarter_num("一") == 1
    assert cn_quarter_num("四") == 4


def test_to_period():
    assert to_period(2026, 1) == "2026Q1"
    assert to_period(2024, 4) == "2024Q4"


def test_parse_roc_date_minguo():
    # 民國 115 年 5 月 19 日 → 西元 2026-05-19
    assert parse_roc_date("法人說明會 中華民國115年5月19日 舉行") == "2026-05-19"


def test_parse_roc_date_western():
    assert parse_roc_date("會議日期 2026年5月19日") == "2026-05-19"


def test_parse_roc_date_none():
    assert parse_roc_date("沒有日期的字串") == ""


def test_build_filename_zh_presentation():
    d = Doc(
        stock_id="2891", company="中信金控", doc_type="presentation",
        fiscal_period="2026Q1", lang="zh", event_date="2026-05-19",
        date_source="pdf_first_page", source_url="u", source_page="p",
    )
    assert build_filename(d, 1) == "2891_20260519M001_2026Q1_concall_presentation.pdf"


def test_build_filename_en_transcript_seq2():
    d = Doc(
        stock_id="2330", company="台積電", doc_type="transcript",
        fiscal_period="2025Q4", lang="en", event_date="2026-01-16",
        date_source="source_listing", source_url="u", source_page="p",
    )
    assert build_filename(d, 2) == "2330_20260116E002_2025Q4_concall_transcript.pdf"


def test_build_filename_unknown_date():
    d = Doc(
        stock_id="2891", company="中信金控", doc_type="presentation",
        fiscal_period="2026Q1", lang="zh", event_date="",
        date_source="unknown", source_url="u", source_page="p",
    )
    assert build_filename(d, 1) == "2891_00000000M001_2026Q1_concall_presentation.pdf"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ec_model.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ec_model'`.

- [ ] **Step 3: Implement ec_model.py**

```python
"""法說會下載：值物件 + 期別/日期正規化 + 檔名產生（純函式、無 I/O）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

LANG_FLAG = {"zh": "M", "en": "E"}  # M=中文 E=英文（使用者指定）
_MONTH_Q = {"03": 1, "06": 2, "09": 3, "12": 4, "3": 1, "6": 2, "9": 3}
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
    return _MONTH_Q[mm.zfill(2)] if mm.zfill(2) in _MONTH_Q else _MONTH_Q[mm]


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ec_model.py -q`
Expected: 8 passed.

- [ ] **Step 5: Lint**

Run: `uv run ruff check .claude/skills/fetch-tw-earnings-call/scripts/ec_model.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/fetch-tw-earnings-call/scripts/ec_model.py tests/test_ec_model.py
git commit -m "feat(skill): ec_model period/date/filename helpers (TDD)"
```

---

## Task 3: `ec_companies` — stock_id → vendor registry

**Files:**
- Create: `.claude/skills/fetch-tw-earnings-call/scripts/ec_companies.py`
- Test: `tests/test_ec_model.py` (append registry tests here to avoid a one-test file)

- [ ] **Step 1: Write the failing tests (append to tests/test_ec_model.py)**

```python
from ec_companies import lookup


def test_lookup_known_company_ctbc():
    info = lookup("2891")
    assert info is not None
    assert info["name"] == "中信金控"
    assert info["vendor"] == "todayir"
    assert "{year}" in info["page_tmpl"]


def test_lookup_unknown_returns_none():
    assert lookup("9999") is None
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_ec_model.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ec_companies'`.

- [ ] **Step 3: Implement ec_companies.py**

```python
"""stock_id → 公司名 + IR 廠商 + 頁面樣板 的小註冊表。

只列已知 vendor adapter 可處理的公司；未列者由 MOPS 底層處理。
固定 5 檔（2308/2317/2330/2454/3034）的 vendor 待各自確認後補上（先留 None）。
"""
from __future__ import annotations

_REGISTRY: dict[str, dict] = {
    "2891": {
        "name": "中信金控",
        "vendor": "todayir",
        "page_tmpl": "https://ir.ctbcholding.com/c/financial_analyst?year={year}",
    },
}


def lookup(stock_id: str) -> dict | None:
    return _REGISTRY.get(stock_id)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_ec_model.py -q`
Expected: all passed (10 total).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/fetch-tw-earnings-call/scripts/ec_companies.py tests/test_ec_model.py
git commit -m "feat(skill): ec_companies registry with 2891/todayir"
```

---

## Task 4: `ec_todayir` adapter — parse IR page into Docs (fixture-driven)

**Files:**
- Create: `tests/fixtures/ctbc_financial_analyst_2026.html`
- Create: `.claude/skills/fetch-tw-earnings-call/scripts/ec_todayir.py`
- Test: `tests/test_ec_todayir.py`

- [ ] **Step 1: Capture the fixture from the live page**

```bash
mkdir -p tests/fixtures
curl -s -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36" \
  "https://ir.ctbcholding.com/c/financial_analyst?year=2026" \
  -o tests/fixtures/ctbc_financial_analyst_2026.html
grep -c "todayir.com" tests/fixtures/ctbc_financial_analyst_2026.html
```
Expected: count ≥ 1 (the 2026 第一季 法說會簡報 links are present).

- [ ] **Step 2: Write the failing test**

```python
"""TodayIR adapter：從存檔 HTML 抽出法說會簡報連結（無網路，注入 fake http_get）。"""
from __future__ import annotations

from pathlib import Path

import ec_todayir

FIXTURE = Path(__file__).parent / "fixtures" / "ctbc_financial_analyst_2026.html"
REGISTRY = {
    "name": "中信金控",
    "vendor": "todayir",
    "page_tmpl": "https://ir.ctbcholding.com/c/financial_analyst?year={year}",
}


def _fake_http_get(_url: str) -> bytes:
    return FIXTURE.read_bytes()


def test_supports_known_vendor():
    assert ec_todayir.supports("2891", REGISTRY) is True
    assert ec_todayir.supports("2330", {"vendor": "other"}) is False


def test_fetch_extracts_q1_presentation():
    docs = ec_todayir.fetch("2891", [2026], _fake_http_get, REGISTRY)
    # 同檔在頁面列兩次（iframe+下載鈕），adapter 先回原始（含重複），url 去重後每季一筆 zh
    periods = {d.fiscal_period for d in docs}
    assert "2026Q1" in periods
    q1 = [d for d in docs if d.fiscal_period == "2026Q1"]
    assert all(d.doc_type == "presentation" for d in q1)
    assert all(d.lang == "zh" for d in q1)               # CTBC 檔名 _tc → 中文
    assert all(d.source_url.endswith(".pdf") for d in q1)
    assert all(d.stock_id == "2891" and d.company == "中信金控" for d in q1)
```

- [ ] **Step 3: Run to verify fail**

Run: `uv run pytest tests/test_ec_todayir.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ec_todayir'`.

- [ ] **Step 4: Implement ec_todayir.py**

```python
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
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_ec_todayir.py -q`
Expected: passed.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check .claude/skills/fetch-tw-earnings-call/scripts/ec_todayir.py
git add .claude/skills/fetch-tw-earnings-call/scripts/ec_todayir.py tests/test_ec_todayir.py tests/fixtures/ctbc_financial_analyst_2026.html
git commit -m "feat(skill): TodayIR adapter, fixture-driven (TDD)"
```

---

## Task 5: Orchestration core — merge + md5 dedupe (pure function)

**Files:**
- Create: `.claude/skills/fetch-tw-earnings-call/scripts/fetch_earnings_call.py`
- Test: `tests/test_fetch_earnings_call.py`

- [ ] **Step 1: Write the failing test**

```python
"""編排層的純邏輯：依內容 md5 去重、同 (period,lang) 流水號。"""
from __future__ import annotations

import hashlib

from ec_model import Doc
from fetch_earnings_call import assign_filenames, dedupe_by_content


def _doc(period="2026Q1", lang="zh", url="u1", date="2026-05-19"):
    return Doc("2891", "中信金控", "presentation", period, lang, date,
               "source_listing", url, "p")


def test_dedupe_drops_identical_bytes():
    a, b = _doc(url="u1"), _doc(url="u2")           # 不同 URL、相同內容
    blobs = {"u1": b"PDFDATA", "u2": b"PDFDATA"}
    kept = dedupe_by_content([a, b], blobs)
    assert len(kept) == 1


def test_dedupe_keeps_distinct_bytes():
    a, b = _doc(url="u1"), _doc(url="u2")
    blobs = {"u1": b"AAA", "u2": b"BBB"}
    assert len(dedupe_by_content([a, b], blobs)) == 2


def test_assign_filenames_sequences_same_period_lang():
    a, b = _doc(url="u1"), _doc(url="u2")
    blobs = {"u1": b"AAA", "u2": b"BBB"}
    named = assign_filenames([a, b], blobs)
    names = sorted(n for _, n in named)
    assert names[0].endswith("M001_2026Q1_concall_presentation.pdf")
    assert names[1].endswith("M002_2026Q1_concall_presentation.pdf")


def test_assign_filenames_separates_lang_sequence():
    zh, en = _doc(lang="zh", url="u1"), _doc(lang="en", url="u2")
    blobs = {"u1": b"AAA", "u2": b"BBB"}
    named = dict((d.source_url, n) for d, n in assign_filenames([zh, en], blobs))
    assert "M001" in named["u1"]
    assert "E001" in named["u2"]
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_fetch_earnings_call.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fetch_earnings_call'`.

- [ ] **Step 3: Implement the pure core in fetch_earnings_call.py**

```python
#!/usr/bin/env python3
"""抓台股法說會簡報/逐字稿（中英），跨股票代號。

混合來源：vendor adapter（TodayIR…）+ MOPS 法人說明會一覽表底層 → md5 去重合併。
繞過 MOPS 反爬：直接打公司 IR 權威來源。輸出 data/<stock_id>_<name>/ + manifest.json。
本檔含可單元測的純邏輯（dedupe / assign_filenames）與 I/O 編排（main）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

import ec_companies
import ec_mops
import ec_todayir
from ec_model import Doc, build_filename, parse_roc_date

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
ADAPTERS = [ec_todayir]


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (trusted IR hosts)
        return r.read()


def dedupe_by_content(docs: list[Doc], blobs: dict[str, bytes]) -> list[Doc]:
    """同內容（md5 相同）只留第一筆；blobs 以 source_url 取位元組。"""
    seen: set[str] = set()
    kept: list[Doc] = []
    for d in docs:
        data = blobs.get(d.source_url)
        if data is None:
            continue
        h = hashlib.md5(data).hexdigest()  # noqa: S324 (僅去重)
        if h in seen:
            continue
        seen.add(h)
        kept.append(d)
    return kept


def assign_filenames(docs: list[Doc], blobs: dict[str, bytes]) -> list[tuple[Doc, str]]:
    """去重後依 (event_date, lang) 給 001+ 流水並產生檔名。"""
    kept = dedupe_by_content(docs, blobs)
    counter: dict[tuple[str, str], int] = defaultdict(int)
    named: list[tuple[Doc, str]] = []
    for d in sorted(kept, key=lambda x: (x.fiscal_period, x.lang, x.source_url)):
        key = (d.event_date, d.lang)
        counter[key] += 1
        named.append((d, build_filename(d, counter[key])))
    return named
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_fetch_earnings_call.py -q`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/fetch-tw-earnings-call/scripts/fetch_earnings_call.py tests/test_fetch_earnings_call.py
git commit -m "feat(skill): orchestration core dedupe + filename sequencing (TDD)"
```

> Note: this step imports `ec_mops` (Task 6) at module top. Until Task 6 lands, run the
> Task-5 tests with `ec_mops` stubbed: create a temporary
> `.claude/skills/fetch-tw-earnings-call/scripts/ec_mops.py` containing
> `def fetch(stock_id, years, http_get): return []` and replace it in Task 6.
> Create that stub now as part of Step 3.

---

## Task 6: `ec_mops` base source — discover endpoint, capture fixture, parse

> **This is a discovery task.** MOPS was revamped (GET `t100sb02_1` → 302); the live
> request shape must be captured before writing the parser. The steps below discover it,
> save a fixture, then TDD the parser against that fixture. If MOPS proves infeasible in a
> time-box, ship `fetch()` returning `[]` with a logged warning — the TodayIR path still
> works (graceful degradation per spec §5).

**Files:**
- Create: `tests/fixtures/mops_t100sb02_2891.<ext>` (ext = `.json` or `.html` per discovery)
- Replace: `.claude/skills/fetch-tw-earnings-call/scripts/ec_mops.py` (stub from Task 5)
- Test: `tests/test_ec_mops.py`

- [ ] **Step 1: Discover the live MOPS 法人說明會一覽表 endpoint**

Open `https://mops.twse.com.tw/mops/#/web/t100sb02_1` in a browser (or the agent-browser
skill), pick a company, and capture the XHR the page issues (DevTools → Network). Record:
the request URL, method, headers, and POST body (stock id `2891`, year as 民國, e.g. `115`).
Then reproduce it with curl, e.g.:

```bash
curl -s -X POST "<DISCOVERED_URL>" \
  -H "Content-Type: application/json" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36" \
  -d '<DISCOVERED_BODY_WITH_2891>' \
  -o tests/fixtures/mops_t100sb02_2891.json
head -c 600 tests/fixtures/mops_t100sb02_2891.json
```
Expected: a non-empty response listing 中信金 法人說明會 records (date + 簡報 link or an id
to build the link). Save it verbatim as the fixture. Note the JSON path / HTML structure for
`date` and `presentation url` in a comment at the top of `ec_mops.py`.

- [ ] **Step 2: Write the failing test against the captured fixture**

```python
"""MOPS 法人說明會一覽表解析（無網路，注入 fake http_get 回存檔 fixture）。"""
from __future__ import annotations

from pathlib import Path

import ec_mops

FIXTURE = Path(__file__).parent / "fixtures" / "mops_t100sb02_2891.json"


def _fake_http_get(_url: str) -> bytes:
    return FIXTURE.read_bytes()


def test_fetch_returns_presentation_docs():
    docs = ec_mops.fetch("2891", [2026], _fake_http_get)
    assert docs, "should parse at least one record from the fixture"
    d = docs[0]
    assert d.stock_id == "2891"
    assert d.doc_type == "presentation"
    assert d.fiscal_period.endswith(("Q1", "Q2", "Q3", "Q4"))
    assert d.source_url.startswith("http")
    assert d.event_date == "" or len(d.event_date) == 10  # ISO or unknown
    assert d.date_source in ("source_listing", "unknown")
```

- [ ] **Step 3: Run to verify fail**

Run: `uv run pytest tests/test_ec_mops.py -q`
Expected: FAIL (stub returns `[]`, so `assert docs` fails) or `ModuleNotFoundError` if stub absent.

- [ ] **Step 4: Implement ec_mops.py against the discovered shape**

Replace the stub. Skeleton to fill using the JSON path / HTML structure recorded in Step 1
(this is the one place whose exact field access depends on the discovered response; wire the
two extraction points marked below):

```python
"""MOPS 法人說明會一覽表（集中式底層，任意股票代號可用）。

來源：公開資訊觀測站 t100sb02_1。改版後走前端 API（POST），端點/欄位於 Step 1 實測確認。
只回 presentation（MOPS 不提供逐字稿）；event_date 取自一覽表日期欄（date_source=source_listing）。
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable

from ec_model import Doc, month_to_quarter, parse_roc_date, to_period

# 以民國年查詢；MOPS 端點與 body 於實作 Step 1 確認後填入。
_ENDPOINT = "<DISCOVERED_URL>"


def _build_body(stock_id: str, roc_year: int) -> str:
    # 對齊 Step 1 實測的 POST body 欄位名。
    return json.dumps({"companyId": stock_id, "year": str(roc_year)})


def fetch(stock_id: str, years: Iterable[int], http_get: Callable[[str], bytes]) -> list[Doc]:
    out: list[Doc] = []
    for y in years:
        roc = y - 1911
        # http_get 在測試時被替換為回 fixture；正式時編排層傳入會 POST 的 client。
        raw = http_get(_ENDPOINT)  # 正式 client 需帶 _build_body(stock_id, roc)
        records = _parse(raw, stock_id)
        out.extend(records)
    return out


def _parse(raw: bytes, stock_id: str) -> list[Doc]:
    data = json.loads(raw.decode("utf-8", "replace"))
    rows = data["result"]["data"]          # <-- EXTRACTION POINT 1: 依實測 JSON path 調整
    docs: list[Doc] = []
    for row in rows:
        date_iso = parse_roc_date(row.get("date", ""))           # 一覽表日期欄
        url = row["presentationUrl"]        # <-- EXTRACTION POINT 2: 依實測欄位名調整
        # period：MOPS 以法說對應季別；若僅有日期，依月份推季。
        if date_iso:
            q = month_to_quarter(date_iso[5:7])
            period = to_period(int(date_iso[:4]), q)
        else:
            period = ""
        docs.append(Doc(
            stock_id=stock_id, company=row.get("companyName", ""),
            doc_type="presentation", fiscal_period=period, lang="zh",
            event_date=date_iso, date_source="source_listing" if date_iso else "unknown",
            source_url=url, source_page=_ENDPOINT,
        ))
    return [d for d in docs if d.source_url and d.fiscal_period]
```

If discovery in Step 1 shows MOPS is HTML (not JSON), parse with a regex over the saved HTML
instead of `json.loads`; keep the same `Doc` output. If MOPS is infeasible in the time-box,
implement `fetch` as `return []` with a `import logging; logging.warning("MOPS base unavailable; vendor adapters only")`
and mark `test_ec_mops.py` with `pytest.mark.skip(reason="MOPS endpoint pending")`.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_ec_mops.py -q`
Expected: passed (or skipped with reason if MOPS deferred).

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check .claude/skills/fetch-tw-earnings-call/scripts/ec_mops.py
git add .claude/skills/fetch-tw-earnings-call/scripts/ec_mops.py tests/test_ec_mops.py tests/fixtures/mops_t100sb02_2891.*
git commit -m "feat(skill): MOPS 法人說明會一覽表 base source (discovery + parser)"
```

---

## Task 7: CLI wiring — resolve sources, download, event-date, manifest

**Files:**
- Modify: `.claude/skills/fetch-tw-earnings-call/scripts/fetch_earnings_call.py` (add I/O fns + `main`)

- [ ] **Step 1: Add event-date extraction, resolver, downloader, manifest writer, and main**

Append to `fetch_earnings_call.py`:

```python
def event_date_from_pdf(pdf_bytes: bytes) -> tuple[str, str]:
    """用 pdftotext 抽首頁日期 → (ISO, 'pdf_first_page')；失敗回 ('', 'unknown')。"""
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf_bytes)
        f.flush()
        try:
            txt = subprocess.run(
                ["pdftotext", "-f", "1", "-l", "1", "-layout", f.name, "-"],
                capture_output=True, text=True, check=False, timeout=30,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return "", "unknown"
    iso = parse_roc_date(txt)
    return (iso, "pdf_first_page") if iso else ("", "unknown")


def resolve_docs(stock_id: str, years: list[int]) -> tuple[str, list[Doc]]:
    """跑命中的 vendor adapter + MOPS 底層，回 (company_name, docs)。"""
    info = ec_companies.lookup(stock_id)
    docs: list[Doc] = []
    company = info["name"] if info else stock_id
    for ad in ADAPTERS:
        if info and ad.supports(stock_id, info):
            docs += ad.fetch(stock_id, years, http_get, info)
    docs += ec_mops.fetch(stock_id, years, http_get)
    return company, docs


def run(stock_id: str, years: list[int], out_dir: Path) -> list[dict]:
    company, docs = resolve_docs(stock_id, years)
    if not docs:
        print(f"查無 {stock_id} 的法說會記錄（已試 vendor adapter + MOPS 底層）。", file=sys.stderr)
        return []
    blobs = {d.source_url: http_get(d.source_url) for d in {d.source_url: d for d in docs}.values()}
    # 補 event_date（adapter 來源沒日期者，用 PDF 首頁）
    enriched: list[Doc] = []
    for d in docs:
        if not d.event_date and d.source_url in blobs:
            iso, src = event_date_from_pdf(blobs[d.source_url])
            d = Doc(**{**d.__dict__, "event_date": iso, "date_source": src})
        enriched.append(d)
    named = assign_filenames(enriched, blobs)

    out_dir.mkdir(parents=True, exist_ok=True)
    fetched_at = date.today().isoformat()
    manifest: list[dict] = []
    n_transcript = 0
    for d, fname in named:
        data = blobs[d.source_url]
        (out_dir / fname).write_bytes(data)
        n_transcript += d.doc_type == "transcript"
        manifest.append({
            "file": fname, "stock_id": d.stock_id, "company": company,
            "doc_type": d.doc_type, "fiscal_period": d.fiscal_period, "lang": d.lang,
            "event_date": d.event_date, "date_source": d.date_source,
            "source_url": d.source_url, "source_page": d.source_page,
            "fetched_at": fetched_at, "md5": hashlib.md5(data).hexdigest(),  # noqa: S324
            "bytes": len(data),
        })
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"下載 {len(manifest)} 份到 {out_dir}/（presentation {len(manifest)-n_transcript}、transcript {n_transcript}）")
    if n_transcript == 0:
        print(f"註：{company}（{stock_id}）無公開 transcript，manifest 僅列簡報。")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-id", required=True)
    ap.add_argument("--from", dest="y_from", type=int, default=2021)
    ap.add_argument("--to", dest="y_to", type=int, default=date.today().year)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    years = list(range(args.y_from, args.y_to + 1))
    info = ec_companies.lookup(args.stock_id)
    name = info["name"] if info else args.stock_id
    out = Path(args.out) if args.out else Path("data") / f"{args.stock_id}_{name}"
    run(args.stock_id, years, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke test against live CTBC (network)**

Run:
```bash
python .claude/skills/fetch-tw-earnings-call/scripts/fetch_earnings_call.py \
  --stock-id 2891 --from 2025 --to 2026 --out /tmp/ec_smoke
ls /tmp/ec_smoke && python3 -c "import json; m=json.load(open('/tmp/ec_smoke/manifest.json')); print(len(m), m[0]['file'])"
```
Expected: PDFs named like `2891_20260519M001_2026Q1_concall_presentation.pdf`, manifest entries
carry `event_date`, `source_url`, `fetched_at`; the "無公開 transcript" note prints for 2891.

- [ ] **Step 3: Full unit suite + lint**

Run: `uv run pytest -q && uv run ruff check .claude/skills/fetch-tw-earnings-call/scripts/`
Expected: all pass, no lint errors.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/fetch-tw-earnings-call/scripts/fetch_earnings_call.py
git commit -m "feat(skill): CLI resolve+download+manifest with PDF event-date"
```

---

## Task 8: Install personal copy + retire old script reference

**Files:**
- Create: `~/.claude/skills/fetch-tw-earnings-call/` (copy of project skill)
- Modify: `scripts/fetch_ctbc_earnings_call.py` (add deprecation note pointing to the skill)

- [ ] **Step 1: Copy the skill to the personal dir for cross-project use**

```bash
rm -rf ~/.claude/skills/fetch-tw-earnings-call
cp -R .claude/skills/fetch-tw-earnings-call ~/.claude/skills/fetch-tw-earnings-call
ls ~/.claude/skills/fetch-tw-earnings-call/scripts
```
Expected: the five `ec_*.py`/`fetch_earnings_call.py` modules are present.

- [ ] **Step 2: Add a deprecation pointer to the old CTBC script**

Edit the module docstring of `scripts/fetch_ctbc_earnings_call.py`, adding at the end:

```python
# 已被 .claude/skills/fetch-tw-earnings-call/ 取代（跨股票代號 + 中英 + manifest）。
# 本檔保留作 TodayIR 解析的參考起點，不再維護。
```

- [ ] **Step 3: Commit**

```bash
git add scripts/fetch_ctbc_earnings_call.py
git commit -m "chore(skill): install personal copy + deprecate single-company script"
```

> The `~/.claude` copy is intentionally untracked by this repo. Re-run Step 1 whenever the
> project skill changes — project version is canonical.

---

## Self-Review Notes (filled by author)

- **Spec coverage:** §2 architecture → Tasks 1,4,6,7; §3 naming → Task 2 `build_filename` + Task 5
  sequencing; §4 transcript/lang → Task 4 `_lang_of`/`_doc_type_of` + Task 7 transcript note;
  §5 errors/dedupe/MOPS risk → Task 5 dedupe + Task 6 discovery+fallback + Task 7 "查無"; §6 tests
  → Tasks 2–6; §7 packaging → Tasks 1,8.
- **Known soft spot:** Task 6 MOPS extraction points depend on live discovery (documented, with
  graceful `[]` fallback so the skill still ships value via TodayIR).
- **Type consistency:** `Doc` field names and `http_get(url)->bytes`, `fetch(stock_id, years, http_get[, registry])`,
  `supports(stock_id, registry)` signatures are used identically across Tasks 4–7.
```
