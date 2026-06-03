"""Compressor 抽象層（D8）。

- :class:`DeterministicCompressor`：常駐、token-free 基線。只「移除」不「新增」
  （去 boilerplate 前綴、壓白、去重複/空行）→ 壓後 token ≤ 原文，且保留
  ``[source_id]`` 標記，引用接地不破。誠實量到多少報多少（不 game ≥50%）。
- :func:`make_llmlingua_compressor`：真實 LLMLingua backend；未安裝 → 明確報錯。
- :func:`active_compressor`：鏡像 :func:`polaris.llm.gemini.active_llm` ——
  ``POLARIS_USE_LLMLINGUA`` 啟用且裝得起 → LLMLingua；否則退確定性。
"""
from __future__ import annotations

import os
import re
from typing import Protocol, runtime_checkable

#: 各節點 stub 注入的 boilerplate 前綴（半形 / 全形括號皆涵蓋）
_BOILERPLATE = ("（v0 stub）", "(v0 stub)")
#: 行內連續空白（不含換行）
_INLINE_WS = re.compile(r"[ \t　]+")


@runtime_checkable
class Compressor(Protocol):
    name: str

    def compress(self, text: str) -> str: ...


class DeterministicCompressor:
    """純 Python、token-free 的保守壓縮基線。"""

    name = "deterministic"

    def compress(self, text: str) -> str:
        if not text:
            return ""
        for marker in _BOILERPLATE:
            text = text.replace(marker, "")
        seen: set[str] = set()
        out: list[str] = []
        for raw in text.splitlines():
            line = _INLINE_WS.sub(" ", raw).strip()
            if not line or line in seen:
                continue
            seen.add(line)
            out.append(line)
        return "\n".join(out)


class _LLMLinguaCompressor:
    """真實 LLMLingua backend 的薄包裝。

    需 ``polaris-desk[llmlingua]``（torch+transformers+llmlingua，~2GB），故
    **不在 CI 執行**；本機跑 POC runner 量 ≥50% 時才會走到。介面與
    :class:`DeterministicCompressor` 相同 → 量測 harness 無須改動。
    """

    name = "llmlingua"

    def __init__(self, compressor: object, rate: float = 0.5) -> None:
        self._c = compressor
        self._rate = rate

    def compress(self, text: str) -> str:  # pragma: no cover - 需本機重依賴
        if not text:
            return ""
        result = self._c.compress_prompt(text, rate=self._rate)  # type: ignore[attr-defined]
        if isinstance(result, dict):
            return str(result.get("compressed_prompt", text))
        return str(result)


def make_llmlingua_compressor(rate: float = 0.5) -> _LLMLinguaCompressor:
    """建立真實 LLMLingua backend；未安裝 → RuntimeError。"""
    try:
        from llmlingua import PromptCompressor  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "llmlingua 未安裝；請 `uv pip install -e '.[llmlingua]'` 後於本機執行 POC。"
        ) from exc
    return _LLMLinguaCompressor(PromptCompressor(), rate=rate)  # pragma: no cover


def _llmlingua_enabled() -> bool:
    return os.getenv("POLARIS_USE_LLMLINGUA", "").strip().lower() in ("1", "true", "yes")


def active_compressor() -> Compressor:
    """選用的壓縮器：啟用且裝得起 LLMLingua → 真實 backend；否則確定性基線。"""
    if _llmlingua_enabled():
        try:
            return make_llmlingua_compressor()
        except Exception:  # noqa: BLE001 — 裝不起就優雅退確定性
            pass
    return DeterministicCompressor()


__all__ = [
    "Compressor",
    "DeterministicCompressor",
    "active_compressor",
    "make_llmlingua_compressor",
]
