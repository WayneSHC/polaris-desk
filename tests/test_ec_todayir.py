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
    periods = {d.fiscal_period for d in docs}
    assert "2026Q1" in periods
    q1 = [d for d in docs if d.fiscal_period == "2026Q1"]
    assert all(d.doc_type == "presentation" for d in q1)
    assert all(d.lang == "zh" for d in q1)
    assert all(d.source_url.endswith(".pdf") for d in q1)
    assert all(d.stock_id == "2891" and d.company == "中信金控" for d in q1)
