"""Deep Research ReAct prompt 機制（R2 W3 D13）。

D15 的 ReAct loop 會消費這裡的 contract：
- :data:`REACT_SYSTEM_PROMPT`（system_instruction，來自中央 registry）。
- :func:`build_react_prompt`：組裝 user-content（工具目錄 + scratchpad + 問題）。
- :func:`parse_react_action`：解析模型輸出的 Action / Action Input；**格式錯誤安全退 finish**。
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from polaris.graph.prompts import REACT_SYSTEM_PROMPT

__all__ = [
    "REACT_SYSTEM_PROMPT",
    "ReActTool",
    "DEFAULT_TOOLS",
    "render_tools",
    "build_react_prompt",
    "ReActAction",
    "parse_react_action",
]


@dataclass(frozen=True)
class ReActTool:
    name: str
    description: str
    input_hint: str


#: v0 工具集：search（檢索接地證據）、finish（收尾輸出結論）。
DEFAULT_TOOLS: tuple[ReActTool, ...] = (
    ReActTool(
        "search",
        "檢索已入庫的法說稿 / 財報 / 新聞，取得可溯源的引用片段。",
        "查詢字串（公司 / 指標 / 期間）",
    ),
    ReActTool(
        "finish",
        "已蒐集足夠（≥3 條）可溯源引用，輸出最終結論。",
        "最終結論文字",
    ),
)


def render_tools(tools: Sequence[ReActTool] = DEFAULT_TOOLS) -> str:
    return "\n".join(f"- {t.name}：{t.description}（輸入：{t.input_hint}）" for t in tools)


def _render_step(step: Mapping, i: int) -> str:
    return (
        f"# 第 {i} 輪\n"
        f"Thought: {step.get('thought', '')}\n"
        f"Action: {step.get('action', '')}\n"
        f"Action Input: {step.get('action_input', '')}\n"
        f"Observation: {step.get('observation', '')}"
    )


def build_react_prompt(
    question: str,
    react_steps: Sequence[Mapping] = (),
    tools: Sequence[ReActTool] = DEFAULT_TOOLS,
) -> str:
    """組裝 ReAct 下一輪的 user-content（system_instruction 走 REACT_SYSTEM_PROMPT）。"""
    parts = [
        f"研究問題：{question}",
        "可用工具：\n" + render_tools(tools),
    ]
    if react_steps:
        scratch = "\n\n".join(_render_step(s, i) for i, s in enumerate(react_steps, 1))
        parts.append("先前進度：\n" + scratch)
    parts.append(
        "請輸出下一個 Thought 與 Action。"
        "若已蒐集 ≥3 條可溯源引用且足以回答，用 Action: finish。"
    )
    return "\n\n".join(parts)


@dataclass(frozen=True)
class ReActAction:
    tool: str
    tool_input: str
    is_finish: bool


_ACTION_RE = re.compile(r"action\s*:\s*([a-zA-Z]+)", re.IGNORECASE)


def parse_react_action(text: str | None) -> ReActAction:
    """解析模型輸出的 Action / Action Input。

    無法解析出 Action（格式錯誤 / 空輸入）→ 安全退 ``finish``，確保 loop 必能終止。
    """
    raw = text or ""
    match = _ACTION_RE.search(raw)
    if not match:
        return ReActAction(tool="finish", tool_input="", is_finish=True)

    tool = match.group(1).lower()
    # Action Input 取「Action Input:」之後全部內容（容許多行結論）。
    idx = raw.lower().find("action input:")
    tool_input = raw[idx + len("action input:") :].strip() if idx >= 0 else ""
    return ReActAction(tool=tool, tool_input=tool_input, is_finish=(tool == "finish"))
