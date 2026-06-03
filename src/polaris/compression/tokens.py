"""token 計數抽象層（D8）。

`count_tokens` 優先用 tiktoken ``cl100k_base``（離線、確定性）；缺套件時退
確定性 regex 估計（CJK 逐字 + latin 詞/標點）。永不 raise，空字串 → 0。

量測 token 省幅時，「相對比例」比「絕對 tokenizer」更重要——只要同一個
counter 同時量原文與壓縮文，省幅就有意義；故 tiktoken 與估計器皆可。
"""
from __future__ import annotations

import re
from typing import Any

#: CJK / 假名逐字 ｜ latin 詞（含數字底線）｜ 其餘非空白單一字元（標點）
_TOKEN_RE = re.compile(r"[一-鿿぀-ヿ가-힯]|[A-Za-z0-9_]+|[^\sA-Za-z0-9_]")

_UNSET: Any = object()
_ENCODER: Any = _UNSET


def _get_encoder() -> Any:
    """惰性取得 tiktoken encoder；無套件 / 失敗 → None（快取結果）。"""
    global _ENCODER
    if _ENCODER is _UNSET:
        try:
            import tiktoken

            _ENCODER = tiktoken.get_encoding("cl100k_base")
        except Exception:  # noqa: BLE001 — 任何失敗都退估計器
            _ENCODER = None
    return _ENCODER


def _estimate_tokens(text: str) -> int:
    """確定性 regex 估計：CJK 逐字、latin 詞、標點各算一個 token。"""
    return len(_TOKEN_RE.findall(text or ""))


def count_tokens(text: str | None) -> int:
    """回傳 ``text`` 的 token 數。空 / None → 0，永不 raise。"""
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:  # noqa: BLE001 — encoder 失敗仍退估計器
            return _estimate_tokens(text)
    return _estimate_tokens(text)


__all__ = ["count_tokens"]
