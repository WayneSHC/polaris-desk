"""_structured_calculations 應把 eps/net_income 也餵進 contexts（修 E013 over_hedge 根因）。

EPS 在 financial_metrics 有值，但結構化計算節點原本只抓 revenue/gross_profit → 一旦
presentation chunk 沒撿回 EPS，writer 就沒數字可用而過度保守（E013 日月光/3711）。這條
結構化後路補上 eps/net_income，數字必有來源。store 注入 → 免金鑰、token=0。
"""
from __future__ import annotations

from polaris.graph.nodes.stubs import _structured_calculations


class FakeFinStore:
    """注入用假 financial store：回固定的 3711 2026Q1 指標列。"""

    def __init__(self, rows):
        self._rows = rows

    def list_financials(self, *, ticker, period, granularity):
        return [r for r in self._rows if r["ticker"] == ticker and r["period"] == period]


def _rows():
    return [
        {"ticker": "3711", "period": "2026Q1", "metric_id": "revenue", "value": 173662152.0,
         "unit": "新台幣千元", "source_id": "3711_2026-03-31_finmind_fs"},
        {"ticker": "3711", "period": "2026Q1", "metric_id": "gross_profit", "value": 34849800.0,
         "unit": "新台幣千元", "source_id": "3711_2026-03-31_finmind_fs"},
        {"ticker": "3711", "period": "2026Q1", "metric_id": "eps", "value": 3.24,
         "unit": "新台幣元/股", "source_id": "3711_2026-03-31_finmind_fs"},
        {"ticker": "3711", "period": "2026Q1", "metric_id": "net_income", "value": 14147537.0,
         "unit": "新台幣千元", "source_id": "3711_2026-03-31_finmind_fs"},
    ]


def test_eps_and_net_income_injected_into_calcs_and_contexts():
    store = FakeFinStore(_rows())
    result = _structured_calculations("日月光投控（3711）2026Q1 EPS?", ["2026Q1"], store=store)
    assert result is not None
    calcs, contexts = result
    entry = calcs["3711:2026Q1"]
    assert entry["eps"]["value"] == 3.24
    assert entry["net_income"]["value"] == 14147537.0
    # EPS 數字要能被 writer 引用：contexts 帶該值 + BQ source_id。
    eps_ctx = [c for c in contexts if "3.24" in c["text"]]
    assert eps_ctx, "eps 應進 contexts 供接地"
    assert eps_ctx[0]["source_id"] == "3711_2026-03-31_finmind_fs"


def test_still_derives_margin_and_revenue():
    """回歸：加 eps/net_income 不破壞既有 revenue + 推導毛利率。"""
    store = FakeFinStore(_rows())
    calcs, _ = _structured_calculations("3711 2026Q1 財報", ["2026Q1"], store=store)
    entry = calcs["3711:2026Q1"]
    assert entry["revenue"]["value"] == 173662152.0
    assert "gross_margin_pct" in entry
