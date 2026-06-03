"""D8 — 量測 harness（polaris.compression.measure）。

measure_text / measure_contexts → CompressionResult；省幅數學正確、不除零、
以 writer 的 contexts 攤平邏輯量「真實 prompt payload」。
"""
from __future__ import annotations

from polaris.compression import measure
from polaris.compression.tokens import count_tokens
from polaris.graph.nodes.writer_agent import _format_contexts

CONTEXTS = [
    {"source_id": "s1", "text": "（v0 stub）台積電 2024Q1 法說摘要：營收與毛利率資料。"},
    {"source_id": "s2", "text": "（v0 stub）台積電 2024Q2 法說摘要：營收與毛利率資料。"},
]


class TestMeasureText:
    def test_saved_tokens_and_pct_math(self):
        r = measure.measure_text("（v0 stub）台積電 2025Q1 營收。")
        assert r.saved_tokens == r.original_tokens - r.compressed_tokens
        assert r.saved_pct == round(r.saved_tokens / r.original_tokens * 100, 2)
        assert r.compressor_name == "deterministic"

    def test_saved_pct_positive_on_verbose(self):
        r = measure.measure_text("（v0 stub）台積電。\n（v0 stub）台積電。\n")
        assert r.saved_pct > 0

    def test_empty_text_no_div_by_zero(self):
        r = measure.measure_text("")
        assert r.original_tokens == 0
        assert r.compressed_tokens == 0
        assert r.saved_pct == 0.0


class TestMeasureContexts:
    def test_uses_writer_flattening(self):
        r = measure.measure_contexts(CONTEXTS)
        assert r.original_tokens == count_tokens(_format_contexts(CONTEXTS))

    def test_saved_pct_positive_on_stub_contexts(self):
        # boilerplate「（v0 stub）」移除 → 確定性基線在 stub 語料上有正省幅
        assert measure.measure_contexts(CONTEXTS).saved_pct > 0

    def test_empty_contexts_no_div_by_zero(self):
        assert measure.measure_contexts([]).saved_pct == 0.0


class TestFormatReport:
    def test_contains_key_numbers(self):
        r = measure.measure_contexts(CONTEXTS)
        report = measure.format_report(r)
        assert "deterministic" in report
        assert str(r.saved_pct) in report
        assert str(r.original_tokens) in report
