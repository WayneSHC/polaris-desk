"""金鑰健檢（R2 W1 D5）— 報告 .env 內哪些 API 金鑰真的設定了。

供 `python -m polaris doctor` / `make check-keys` 使用，讓全隊在 G1 前能一眼
確認「GCP·Gemini key 全隊可用」這個閘門項目。判斷沿用
:func:`polaris.llm.gemini.is_real_key`（空 / 空白 / `#` 開頭一律視為未設定）。
"""
from __future__ import annotations

from polaris.config import settings
from polaris.llm.gemini import is_real_key

#: 對外顯示名稱 → Settings 屬性名。
KEY_FIELDS: dict[str, str] = {
    "GEMINI_API_KEY": "gemini_api_key",
    "COHERE_API_KEY": "cohere_api_key",
    "TAVILY_API_KEY": "tavily_api_key",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "OPENAI_API_KEY": "openai_api_key",
}


def key_status() -> dict[str, bool]:
    """回傳 {顯示名稱: 是否已設定真值}。"""
    return {
        name: is_real_key(getattr(settings, attr, ""))
        for name, attr in KEY_FIELDS.items()
    }


__all__ = ["key_status", "KEY_FIELDS"]
