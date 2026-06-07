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
