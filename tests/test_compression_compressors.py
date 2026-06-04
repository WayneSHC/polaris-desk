"""D8 — Compressor 抽象層（polaris.compression.compressors）。

- DeterministicCompressor：常駐、token-free、只「移除」不「新增」→ 壓後 token ≤ 原文，
  且保留 [source_id] 標記（引用接地不破）。
- active_compressor()：鏡像 active_llm()，llmlingua 缺席 / 未啟用 → 退確定性。
- make_llmlingua_compressor()：未安裝時明確報錯（不靜默假裝有真壓縮）。
"""
from __future__ import annotations

import sys
import types

import pytest

from polaris.compression import compressors
from polaris.compression.tokens import count_tokens


def _fake_llmlingua(captured: dict) -> types.ModuleType:
    """假的 llmlingua 模組：記錄 PromptCompressor 的 init kwargs（不載 torch/模型）。"""

    class _FakePromptCompressor:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    mod = types.ModuleType("llmlingua")
    mod.PromptCompressor = _FakePromptCompressor  # type: ignore[attr-defined]
    return mod

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
        # 強制「未安裝」（sys.modules[llmlingua]=None → import 觸發 ImportError），
        # 與本機是否裝了 [llmlingua] extra 無關（測試須確定性、且絕不下載模型）。
        monkeypatch.setitem(sys.modules, "llmlingua", None)
        # 即使要求啟用，未安裝 llmlingua 仍須優雅退確定性（不 raise）
        assert isinstance(
            compressors.active_compressor(), compressors.DeterministicCompressor
        )


class TestMakeLLMLingua:
    def test_raises_when_not_installed(self, monkeypatch):
        # 強制「未安裝」→ 明確報錯（不靜默假裝有真壓縮）。install-independent。
        monkeypatch.setitem(sys.modules, "llmlingua", None)
        with pytest.raises((RuntimeError, ImportError)):
            compressors.make_llmlingua_compressor()

    def test_configures_llmlingua2_multilingual(self, monkeypatch):
        # 用 LLMLingua-2 多語小模型（適用中文）、CPU、啟用 use_llmlingua2。
        captured: dict = {}
        monkeypatch.setitem(sys.modules, "llmlingua", _fake_llmlingua(captured))
        comp = compressors.make_llmlingua_compressor(rate=0.4)
        assert comp.name == "llmlingua"
        assert captured["use_llmlingua2"] is True
        assert captured["device_map"] == "cpu"
        assert "llmlingua-2" in captured["model_name"]

    def test_model_overridable_via_env(self, monkeypatch):
        captured: dict = {}
        monkeypatch.setitem(sys.modules, "llmlingua", _fake_llmlingua(captured))
        monkeypatch.setenv("POLARIS_LLMLINGUA_MODEL", "my/custom-model")
        compressors.make_llmlingua_compressor()
        assert captured["model_name"] == "my/custom-model"

    def test_rate_overridable_via_env(self, monkeypatch):
        # 預設保守 rate=0.5；要量 ≥50% 目標時用 env 調更積極（≈0.33）。
        monkeypatch.setitem(sys.modules, "llmlingua", _fake_llmlingua({}))
        monkeypatch.setenv("POLARIS_LLMLINGUA_RATE", "0.33")
        assert compressors.make_llmlingua_compressor()._rate == 0.33

    def test_rate_default_is_half(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "llmlingua", _fake_llmlingua({}))
        monkeypatch.delenv("POLARIS_LLMLINGUA_RATE", raising=False)
        assert compressors.make_llmlingua_compressor()._rate == 0.5
