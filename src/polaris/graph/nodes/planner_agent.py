"""Planner Agent v0（R2 W1 D2）— 把投研問題拆成有序步驟。

兩條路徑（smart node + 確定性 fallback，見 design 2026-06-02）：
- **LLM 路徑**：有真金鑰時用 Gemini Flash 拆解問題（`llm_plan`）。
- **fallback**：無金鑰 / LLM 失敗 / 空輸出 → 確定性啟發式（`fallback_plan`）。

純函式設計（client 以參數注入），方便單元測試；節點（stubs.planner）
只是薄 wrapper：解析金鑰可用性後呼叫 :func:`make_plan`。
"""
from __future__ import annotations

import re
from typing import Protocol


class _LLM(Protocol):
    def generate(
        self, prompt: str, *, flash: bool = ..., system_instruction: str | None = ...
    ) -> str: ...


SYSTEM_PROMPT = (
    "你是台灣資本市場投研的規劃助手。把使用者的問題拆解成 2–5 個有序、"
    "可執行的步驟（擷取資料 → 計算指標 → 彙整並標引用）。"
    "只輸出步驟本身，每步一行、用數字編號，不要多餘說明。"
    "不得提供任何買賣建議。"
)

# 行首列表標記：`1.` / `2)` / `3、` / `-` / `*` / `•`，後接空白
_MARKER = re.compile(r"^\s*(?:\d+[.)、]|[-*•])\s+")


def _build_prompt(query: str) -> str:
    return (
        f"使用者問題：{query}\n\n"
        "請輸出 2–5 個有序步驟，每步一行，用數字編號（例如「1. …」）。"
    )


def parse_plan(text: str) -> list[str]:
    """把 LLM 文字輸出解析成步驟清單。

    - 有列表標記的行 → 取標記後內容（並丟掉前言等無標記行）。
    - 完全沒有標記 → 退回所有非空白行。
    """
    lines = [ln.strip() for ln in (text or "").splitlines()]
    marked = [_MARKER.sub("", ln).strip() for ln in lines if _MARKER.match(ln)]
    if marked:
        return [s for s in marked if s]
    return [ln for ln in lines if ln]


def fallback_plan(query: str) -> list[str]:  # noqa: ARG001 — v0 用固定步驟，保留 query 介面
    """無金鑰時的確定性計畫（最後一步指向引用接地，守憲法）。"""
    return [
        "擷取與問題相關的法說會 / 財報段落",
        "計算所需財務指標並核對期間",
        "彙整為結論並逐句標註引用來源",
    ]


def llm_plan(query: str, client: _LLM) -> list[str]:
    """用 Gemini Flash 拆解問題並解析成步驟。"""
    raw = client.generate(
        _build_prompt(query), flash=True, system_instruction=SYSTEM_PROMPT
    )
    return parse_plan(raw)


def make_plan(query: str, client: _LLM | None) -> list[str]:
    """有 client 走 LLM；失敗 / 空輸出 / 無 client → fallback。"""
    if client is None:
        return fallback_plan(query)
    try:
        steps = llm_plan(query, client)
    except Exception:  # noqa: BLE001 — LLM 任何失敗都退 fallback，不可讓節點掛掉
        steps = []
    return steps or fallback_plan(query)


__all__ = ["SYSTEM_PROMPT", "parse_plan", "fallback_plan", "llm_plan", "make_plan"]
