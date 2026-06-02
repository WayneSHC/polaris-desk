"""D5 — Gemini 金鑰有效性判斷（修 truthy-placeholder latent bug）。

`.env` 的佔位字串是 `'# 必填…'`：truthy 但無效。`is_real_key` 必須把
空字串 / 純空白 / `#` 開頭一律視為「未設定」，避免下游以為有金鑰卻在
呼叫時才爆。
"""
from __future__ import annotations

from polaris.llm import gemini


class TestIsRealKey:
    def test_empty_string_is_not_real(self):
        assert gemini.is_real_key("") is False

    def test_none_is_not_real(self):
        assert gemini.is_real_key(None) is False

    def test_whitespace_only_is_not_real(self):
        assert gemini.is_real_key("   ") is False

    def test_hash_placeholder_is_not_real(self):
        # 正是 .env 目前的值形態
        assert gemini.is_real_key("# 必填（主力模型 Gemini 3.0 Pro/Flash）") is False

    def test_leading_whitespace_then_hash_is_not_real(self):
        assert gemini.is_real_key("   # still a comment") is False

    def test_realistic_key_is_real(self):
        assert gemini.is_real_key("AIzaSyD-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx") is True


class TestAvailable:
    def test_available_false_for_placeholder(self, monkeypatch):
        from polaris.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "# placeholder")
        assert gemini.available() is False

    def test_available_true_for_real_key(self, monkeypatch):
        from polaris.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "AIzaSyReal123")
        assert gemini.available() is True


class TestActiveLLM:
    def test_active_llm_is_none_without_real_key(self, monkeypatch):
        from polaris.config import settings

        monkeypatch.setattr(settings, "gemini_api_key", "# placeholder")
        assert gemini.active_llm() is None
