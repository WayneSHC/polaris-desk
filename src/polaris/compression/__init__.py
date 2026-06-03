"""Prompt 壓縮 token 省幅量測（R2 W2 D8 LLMLingua POC）。

- :mod:`polaris.compression.tokens`：token 計數抽象（tiktoken + regex fallback）。
- :mod:`polaris.compression.compressors`：Compressor 介面 + 確定性基線 + LLMLingua 選用。
- :mod:`polaris.compression.measure`：量測 harness（contexts → token 省幅報告）。

設計與 Gemini 節點相同的 smart-node 模式：CI / 無 extra 走確定性、token-free 路徑；
裝了 ``[llmlingua]`` extra 才接真實 LLMLingua backend，零結構改動。
"""
from __future__ import annotations

__all__ = ["tokens", "compressors", "measure"]
