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
