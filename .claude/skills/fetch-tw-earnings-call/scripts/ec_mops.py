"""MOPS 底層來源（Task 6 實作；此為暫時 stub 讓 import 解析）。"""
from __future__ import annotations

from collections.abc import Callable, Iterable

from ec_model import Doc


def fetch(stock_id: str, years: Iterable[int], http_get: Callable[[str], bytes]) -> list[Doc]:
    return []
