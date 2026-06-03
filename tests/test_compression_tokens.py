"""D8 — token 計數抽象層（polaris.compression.tokens）。

優先用 tiktoken（離線、確定性）；缺套件時退確定性 regex 估計。
兩條路徑都要確定性、永不 raise、空字串→0。
"""
from __future__ import annotations

from polaris.compression import tokens


class TestCountTokens:
    def test_empty_string_is_zero(self):
        assert tokens.count_tokens("") == 0

    def test_none_is_zero(self):
        assert tokens.count_tokens(None) == 0

    def test_nonempty_is_positive(self):
        assert tokens.count_tokens("台積電 2025 Q1 營收") > 0

    def test_longer_text_has_more_tokens(self):
        short = "台積電營收"
        longer = "台積電 2025 年第一季營收年增率與毛利率趨勢分析"
        assert tokens.count_tokens(longer) > tokens.count_tokens(short)

    def test_is_deterministic(self):
        text = "聯發科最近兩季毛利率趨勢"
        assert tokens.count_tokens(text) == tokens.count_tokens(text)


class TestEstimatorFallback:
    """tiktoken 不可用時，count_tokens 退 regex 估計，仍正常運作。"""

    def test_falls_back_when_no_encoder(self, monkeypatch):
        monkeypatch.setattr(tokens, "_get_encoder", lambda: None)
        n = tokens.count_tokens("台積電 2025 Q1 營收成長")
        assert n > 0

    def test_fallback_is_deterministic(self, monkeypatch):
        monkeypatch.setattr(tokens, "_get_encoder", lambda: None)
        text = "台積電 2025 Q1 營收成長"
        assert tokens.count_tokens(text) == tokens.count_tokens(text)

    def test_estimator_counts_cjk_per_char(self):
        # 4 個中文字 → 至少 4 個 token（逐字計）
        assert tokens._estimate_tokens("台積電好") >= 4

    def test_estimator_empty_is_zero(self):
        assert tokens._estimate_tokens("") == 0
