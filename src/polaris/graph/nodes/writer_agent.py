"""Writer Agent v0（R2 W1 D3）— 依 contexts 產生「帶引用」草稿。

- :func:`build_citations` 把 retriever 的 contexts 轉成 ``Citation``（接地）。
- LLM 路徑用 Gemini **Pro**（撰寫品質優先）；fallback 為確定性草稿。
- 草稿產出後仍會經 Compliance 節點（NFR-031）；本模組**不**自行判合規，
  即使 LLM 越線，攔截責任在 compliance.py（端到端測試驗證）。
"""
from __future__ import annotations

from typing import Any, Protocol

from polaris.graph.state import Citation


class _LLM(Protocol):
    def generate(
        self, prompt: str, *, flash: bool = ..., system_instruction: str | None = ...
    ) -> str: ...


SYSTEM_PROMPT = (
    "你是台灣資本市場投研撰稿助手。只根據提供的引用片段回答，"
    "每個關鍵數字或主張都要標註對應來源（source_id）。"
    "嚴禁提供任何買賣建議；只描述事實、標證據、標矛盾。"
    "找不到依據就明說資料不足，不得臆測。"
)


def build_citations(contexts: list[dict[str, Any]]) -> list[Citation]:
    """contexts → Citation 清單。snippet 取 ``snippet`` 或 ``text``；origin 預設 'stub'。"""
    cites: list[Citation] = []
    for ctx in contexts or []:
        snippet = ctx.get("snippet") or ctx.get("text") or ""
        if not snippet:
            continue
        cites.append(
            Citation(
                source_id=str(ctx.get("source_id", "unknown")),
                snippet=snippet,
                origin=ctx.get("origin", "stub"),
            )
        )
    return cites


def _format_contexts(contexts: list[dict[str, Any]]) -> str:
    lines = []
    for ctx in contexts or []:
        sid = ctx.get("source_id", "unknown")
        text = ctx.get("snippet") or ctx.get("text") or ""
        lines.append(f"[{sid}] {text}")
    return "\n".join(lines) if lines else "（無引用片段）"


def _build_prompt(query: str, contexts: list[dict[str, Any]]) -> str:
    return (
        f"使用者問題：{query}\n\n"
        f"可用引用片段：\n{_format_contexts(contexts)}\n\n"
        "請依據上述片段撰寫結論，並在關鍵主張後標註對應 source_id。"
    )


def fallback_draft(query: str, contexts: list[dict[str, Any]]) -> str:  # noqa: ARG001
    """無金鑰時的確定性草稿：列出引用來源，明標 stub 模式、不含買賣建議。"""
    if contexts:
        srcs = "、".join(str(c.get("source_id", "unknown")) for c in contexts)
        body = f"依據引用來源（{srcs}）整理之事實摘要。"
    else:
        body = "目前無可用引用片段，資料不足。"
    return f"（v0 stub 草稿）{body}本系統僅描述事實與引用，不提供買賣建議。"


def llm_draft(query: str, contexts: list[dict[str, Any]], client: _LLM) -> str:
    """用 Gemini Pro 依 contexts 撰寫草稿。"""
    return client.generate(
        _build_prompt(query, contexts), flash=False, system_instruction=SYSTEM_PROMPT
    )


def make_draft(
    query: str, contexts: list[dict[str, Any]], client: _LLM | None
) -> tuple[str, list[Citation]]:
    """回 (draft, citations)。有 client 走 LLM；失敗 / 空輸出 / 無 client → fallback。"""
    citations = build_citations(contexts)
    if client is None:
        return fallback_draft(query, contexts), citations
    try:
        draft = llm_draft(query, contexts, client)
    except Exception:  # noqa: BLE001 — LLM 任何失敗都退 fallback
        draft = ""
    return (draft.strip() or fallback_draft(query, contexts)), citations


__all__ = [
    "SYSTEM_PROMPT",
    "build_citations",
    "fallback_draft",
    "llm_draft",
    "make_draft",
]
