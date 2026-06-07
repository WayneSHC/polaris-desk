"""MOPS 法人說明會一覽表解析（無網路，注入 fake http_get 回存檔 fixture）。"""
from __future__ import annotations

from pathlib import Path

import ec_mops

FIXTURE = Path(__file__).parent / "fixtures" / "mops_t100sb02_2891.html"


def _fake_http_get(_url: str) -> bytes:
    return FIXTURE.read_bytes()


def test_fetch_parses_quarterly_presentations():
    docs = ec_mops.fetch("2891", [2025], _fake_http_get)
    assert docs
    periods = {d.fiscal_period for d in docs}
    assert {"2024Q4", "2025Q1", "2025Q2", "2025Q3"} <= periods
    langs = {d.lang for d in docs}
    assert langs == {"zh", "en"}
    assert all(d.doc_type == "presentation" for d in docs)
    assert all(d.source_url.startswith("https://mopsov.twse.com.tw/nas/STR/") for d in docs)
    assert all(len(d.event_date) == 10 for d in docs)
    q1_zh = [d for d in docs if d.fiscal_period == "2025Q1" and d.lang == "zh"]
    assert q1_zh and q1_zh[0].source_url.endswith("289120250516M001.pdf")
