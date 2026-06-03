"""量測 harness（D8）：給定文字 / contexts，量壓縮 token 省幅。

`measure_contexts` 刻意重用 writer 的 ``_format_contexts`` 攤平邏輯，量到的就是
**真實會送進 Writer 的 prompt payload**，而非另造一份近似。省幅 = 同一個 counter
同時量原文與壓縮文的相對差，故 tokenizer 絕對值不影響結論。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from polaris.compression.compressors import Compressor, active_compressor
from polaris.compression.tokens import count_tokens

# 重用 Writer 的 contexts→prompt 攤平（量真實 payload；private 但同一 codebase）。
from polaris.graph.nodes.writer_agent import _format_contexts


@dataclass(frozen=True)
class CompressionResult:
    """單次壓縮量測結果。"""

    compressor_name: str
    original_tokens: int
    compressed_tokens: int
    saved_tokens: int
    saved_pct: float


def measure_text(
    text: str,
    *,
    compressor: Compressor | None = None,
    count: Callable[[str | None], int] = count_tokens,
) -> CompressionResult:
    """量單一字串的壓縮省幅。``compressor`` 預設 :func:`active_compressor`。"""
    comp = compressor or active_compressor()
    original = count(text)
    compressed = count(comp.compress(text))
    saved = original - compressed
    pct = round(saved / original * 100, 2) if original else 0.0
    return CompressionResult(
        compressor_name=getattr(comp, "name", "unknown"),
        original_tokens=original,
        compressed_tokens=compressed,
        saved_tokens=saved,
        saved_pct=pct,
    )


def measure_contexts(
    contexts: list[dict[str, Any]],
    *,
    compressor: Compressor | None = None,
    count: Callable[[str | None], int] = count_tokens,
) -> CompressionResult:
    """量 retriever contexts 攤平成 Writer prompt payload 後的壓縮省幅。"""
    return measure_text(_format_contexts(contexts), compressor=compressor, count=count)


def format_report(result: CompressionResult) -> str:
    """把 :class:`CompressionResult` 格式化成可讀報告（POC runner 用）。"""
    return (
        f"壓縮器：{result.compressor_name}\n"
        f"原始 tokens：{result.original_tokens}\n"
        f"壓縮後 tokens：{result.compressed_tokens}\n"
        f"省下 tokens：{result.saved_tokens}\n"
        f"省幅：{result.saved_pct}%"
    )


__all__ = [
    "CompressionResult",
    "measure_text",
    "measure_contexts",
    "format_report",
]
