"""D8 — Compressor 抽象層（polaris.compression.compressors）。

- DeterministicCompressor：常駐、token-free、只「移除」不「新增」→ 壓後 token ≤ 原文，
  且保留 [source_id] 標記（引用接地不破）。
- active_compressor()：鏡像 active_llm()，llmlingua 缺席 / 未啟用 → 退確定性。
- make_llmlingua_compressor()：未安裝時明確報錯（不靜默假裝有真壓縮）。
"""
from __future__ import annotations

import pytest

from polaris.compression import compressors
from polaris.compression.tokens import count_tokens

_VERBOSE = (
    "（v0 stub）台積電 2024Q1 法說摘要：營收與毛利率資料。\n"
    "（v0 stub）台積電 2024Q1 法說摘要：營收與毛利率資料。\n"  # 重複行
    "\n   多餘    空白    片段   \n"
)


class TestDeterministicCompressor:
    def test_empty_returns_empty(self):
        assert compressors.DeterministicCompressor().compress("") == ""

    def test_does_not_increase_tokens(self):
        text = "[stub-2330-2025Q1] 台積電 2025Q1 法說摘要：營收與毛利率資料。"
        out = compressors.DeterministicCompressor().compress(text)
        assert count_tokens(out) <= count_tokens(text)

    def test_reduces_verbose_input(self):
        out = compressors.DeterministicCompressor().compress(_VERBOSE)
        assert count_tokens(out) < count_tokens(_VERBOSE)

    def test_preserves_source_markers(self):
        text = "[stub-2330-2025Q1] （v0 stub）營收資料。"
        out = compressors.DeterministicCompressor().compress(text)
        assert "[stub-2330-2025Q1]" in out

    def test_is_deterministic(self):
        c = compressors.DeterministicCompressor()
        assert c.compress(_VERBOSE) == c.compress(_VERBOSE)

    def test_has_name(self):
        assert compressors.DeterministicCompressor().name == "deterministic"


class TestActiveCompressor:
    def test_returns_deterministic_when_llmlingua_absent(self):
        # 預設環境未裝 llmlingua → 退確定性
        assert isinstance(
            compressors.active_compressor(), compressors.DeterministicCompressor
        )

    def test_env_flag_without_install_still_falls_back(self, monkeypatch):
        monkeypatch.setenv("POLARIS_USE_LLMLINGUA", "1")
        # 即使要求啟用，未安裝 llmlingua 仍須優雅退確定性（不 raise）
        assert isinstance(
            compressors.active_compressor(), compressors.DeterministicCompressor
        )


class TestMakeLLMLingua:
    def test_raises_when_not_installed(self):
        with pytest.raises((RuntimeError, ImportError)):
            compressors.make_llmlingua_compressor()
