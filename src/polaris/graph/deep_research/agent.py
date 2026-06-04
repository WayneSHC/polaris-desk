"""Deep Research v0 — 自寫 ReAct loop（R2 W3 D15）。

純 Python bounded loop（AQ-03 決策 + 用戶選定 v0 編排）：
- **smart**（有金鑰）：`build_react_prompt` → Gemini（包 D7 retry）→ `parse_react_action`。
- **確定性 fallback**（無金鑰 / LLM 失敗）：facet 政策輪流 search 到 ≥min_citations 才 finish。
- evidence 依 source_id 去重累積；迴圈受 `should_continue`（≤max_loops）守門。
- 最終結論一律過 D9 Compliance Agent（NFR-031）。

`search` 為注入式 seam（v0 用 :func:`stub_search`，token-free）；R4 真實
`VectorStore.search` 之後接這即可，loop 不變。
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from polaris.graph.deep_research.react import (
    DEFAULT_TOOLS,
    REACT_SYSTEM_PROMPT,
    ReActAction,
    build_react_prompt,
    parse_react_action,
)
from polaris.graph.deep_research.state import (
    DeepResearchResult,
    ReActStep,
    dedup_evidence,
    is_fully_traceable,
    should_continue,
)
from polaris.graph.nodes import compliance_agent
from polaris.graph.state import Citation
from polaris.retry import call_with_retry

SearchFn = Callable[[str], list[Citation]]

#: 確定性 fallback 政策輪流檢索的面向。
_FACETS = ("營收", "毛利率", "風險與展望")


def stub_search(query: str) -> list[Citation]:
    """確定性、token-free 的 search 工具：不同 query → 不同 source_id。"""
    slug = re.sub(r"\s+", "-", (query or "").strip()) or "query"
    return [
        Citation(
            source_id=f"stub-{slug[:48]}",
            snippet=f"（stub 證據）關於「{query}」的法說 / 財報摘要片段。",
            origin="stub",
        )
    ]


def _deterministic_action(question: str, state: dict, min_citations: int) -> ReActAction:
    if len(state["evidence"]) >= min_citations:
        return ReActAction(tool="finish", tool_input="", is_finish=True)
    facet = _FACETS[state["iteration"] % len(_FACETS)]
    return ReActAction(tool="search", tool_input=f"{question} {facet}", is_finish=False)


def _decide(question: str, state: dict, client, min_citations: int) -> ReActAction:
    """決定下一個行動。有金鑰走 LLM（含 D7 retry）；任何失敗 → 退確定性政策。"""
    if client is not None:
        try:
            steps: Sequence[dict] = [s.model_dump() for s in state["react_steps"]]
            prompt = build_react_prompt(question, steps, DEFAULT_TOOLS)
            raw = call_with_retry(
                lambda: client.generate(
                    prompt, flash=True, system_instruction=REACT_SYSTEM_PROMPT
                )
            )
            return parse_react_action(raw)
        except Exception:  # noqa: BLE001 — fail-to-deterministic（不讓 agent 掛掉）
            pass
    return _deterministic_action(question, state, min_citations)


def _summarize(found: Sequence[Citation]) -> str:
    if not found:
        return "（無新證據）"
    return "取得引用：" + "、".join(c.source_id for c in found)


def _synthesize(question: str, evidence: Sequence[Citation], *, exhausted: bool = False) -> str:
    """確定性收尾結論（不含買賣建議；引用不足誠實標註）。"""
    if not evidence:
        return f"關於「{question}」目前找不到可溯源的引用，資料不足、無法形成結論。"
    # 逐點：一條 evidence 一個 bullet + 來源標記 → 句句可溯源 by construction（D16）。
    points = "\n".join(f"- {c.snippet}（來源：{c.source_id}）" for c in evidence)
    text = (
        f"關於「{question}」的研究摘要（依據 {len(evidence)} 條引用）：\n"
        f"{points}\n"
        "本回答僅描述事實與來源，不提供買賣建議。"
    )
    if exhausted and len(evidence) < 3:
        text += "\n（註：引用不足 3 條，結論暫定、待補證據。）"
    return text


def _act(question: str, state: dict, action: ReActAction, search: SearchFn) -> None:
    if action.is_finish or action.tool == "finish":
        answer = (action.tool_input or "").strip() or _synthesize(question, state["evidence"])
        state["react_steps"].append(
            ReActStep(thought="證據足夠，產出結論", action="finish", action_input=action.tool_input)
        )
        state["final_answer"] = answer
        state["status"] = "answered"
    elif action.tool == "search":
        found = search(action.tool_input or question)
        state["evidence"] = dedup_evidence(state["evidence"], found)
        state["react_steps"].append(
            ReActStep(
                thought=f"需要更多關於「{action.tool_input}」的證據",
                action="search",
                action_input=action.tool_input,
                observation=_summarize(found),
            )
        )
    else:
        # 未知工具 → 安全當 finish（與 parser 的 malformed→finish 一致）
        state["react_steps"].append(
            ReActStep(thought="未知行動，安全收斂", action="finish")
        )
        state["final_answer"] = _synthesize(question, state["evidence"])
        state["status"] = "answered"
    state["iteration"] += 1


def run_deep_research(
    question: str,
    *,
    client=None,
    search: SearchFn = stub_search,
    max_loops: int = 6,
    min_citations: int = 3,
) -> DeepResearchResult:
    """跑通 Deep Research ReAct loop，回 :class:`DeepResearchResult`。"""
    state: dict = {
        "iteration": 0,
        "status": "running",
        "react_steps": [],
        "evidence": [],
        "final_answer": "",
    }
    while should_continue(state, max_loops=max_loops):
        action = _decide(question, state, client, min_citations)
        _act(question, state, action, search)

    if state["status"] != "answered":
        state["status"] = "exhausted"
        if not state["final_answer"]:
            state["final_answer"] = _synthesize(question, state["evidence"], exhausted=True)

    # D16 句句可溯源硬保證：候選答案（含 LLM 自由文）未通過且有 evidence →
    # 改用結構化 grounded 摘要（接地 > 文采；LLM 推理仍保留在 react_steps）。
    if state["evidence"] and not is_fully_traceable(state["final_answer"], state["evidence"]):
        state["final_answer"] = _synthesize(question, state["evidence"])

    # NFR-031：最終結論一律過 D9 Compliance Agent。
    answer, compliance_status = compliance_agent.review(state["final_answer"], client)

    return DeepResearchResult(
        question=question,
        final_answer=answer,
        evidence=state["evidence"],
        react_steps=state["react_steps"],
        iterations=state["iteration"],
        status=state["status"],
        compliance_status=compliance_status,
    )


__all__ = ["stub_search", "run_deep_research", "SearchFn"]
