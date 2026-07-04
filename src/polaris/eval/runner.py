"""執行 Eval 題目並保存可重用的結構化 records。

一般題共用同一個 compiled workflow；場景 2 走 Deep Research。輸出保留完整
引用與 stub 判定，讓評分可重跑而不必再次消耗檢索或回答模型。
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable

from polaris.eval.dataset import EvalItem


@dataclass
class EvalRecord:
    """單題 workflow 結果與評分所需中繼資料。"""

    item: EvalItem
    answer: str
    contexts: list[str] = field(default_factory=list)
    ground_truth: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    compliance_status: str = "unknown"
    citation_count: int = 0
    #: visual_reader 是否觸發（任一 citation origin=='vision'）——#3 觸發門檻校準訊號。
    escalated: bool = False
    context_source: str = "unknown"
    is_stub: bool = False
    is_smoke_test: bool = False

    @property
    def context_count(self) -> int:
        return len(self.contexts)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["item"] = self.item.model_dump()
        data["context_count"] = self.context_count
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalRecord":
        payload = dict(data)
        payload.pop("context_count", None)
        payload["item"] = EvalItem(**payload["item"])
        # 舊 records.jsonl 於 schema 演進後仍可 --reuse-records 重跑：忽略已移除的
        # 欄位，缺少的新欄位交由 dataclass 預設值補上。
        known = {field_def.name for field_def in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in known})


def normalize_contexts(raw_contexts: Any) -> list[str]:
    """將 dict、字串或文件物件統一轉成 RAGAS 接受的 ``list[str]``。"""

    if raw_contexts is None:
        return []
    if isinstance(raw_contexts, str):
        return [raw_contexts.strip()] if raw_contexts.strip() else []
    if isinstance(raw_contexts, dict) or not isinstance(raw_contexts, Iterable):
        raw_contexts = [raw_contexts]

    normalized: list[str] = []
    for context in raw_contexts:
        text = _context_text(context)
        if text:
            normalized.append(text)
    return normalized


def _run_workflow(question: str, *, app: Any | None = None) -> dict[str, Any]:
    if app is None:
        from polaris.graph.workflow import build_workflow

        app = build_workflow()
    return app.invoke({"query": question})


def run_item(
    item: EvalItem,
    *,
    app: Any | None = None,
    deep_research_runner: Callable[[str], Any] | None = None,
) -> EvalRecord:
    """執行單題；可注入 app/Deep Research runner 供測試使用。"""

    if item.scenario == "2":
        result = _run_deep_research(item.question, runner=deep_research_runner)
    else:
        result = (
            _run_workflow(item.question)
            if app is None
            else _run_workflow(item.question, app=app)
        )
    return _record_from_result(item, result)


def run_dataset(
    items: list[EvalItem],
    *,
    app: Any | None = None,
    deep_research_runner: Callable[[str], Any] | None = None,
) -> list[EvalRecord]:
    """執行整批題庫；一般題的 workflow 僅 compile 一次。"""

    if app is None and any(item.scenario != "2" for item in items):
        from polaris.graph.workflow import build_workflow

        app = build_workflow()
    return [
        run_item(item, app=app, deep_research_runner=deep_research_runner)
        for item in items
    ]


def write_records_jsonl(records: list[EvalRecord], path: str | Path) -> Path:
    """保存 workflow 結果，供 ``--reuse-records`` 重跑評分。"""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return output


def read_records_jsonl(path: str | Path) -> list[EvalRecord]:
    records: list[EvalRecord] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(EvalRecord.from_dict(json.loads(line)))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"records JSONL 第 {line_number} 列無效：{exc}") from exc
    if not records:
        raise ValueError(f"records JSONL 為空：{path}")
    return records


def _run_deep_research(
    question: str,
    *,
    runner: Callable[[str], Any] | None,
) -> dict[str, Any]:
    if runner is None:
        from polaris.graph.deep_research.agent import run_deep_research

        runner = run_deep_research
    result = runner(question)
    evidence = list(result.evidence)
    return {
        "answer": result.final_answer,
        "contexts": [{"text": citation.snippet, "origin": citation.origin} for citation in evidence],
        "citations": evidence,
        "compliance_status": result.compliance_status,
    }


def _record_from_result(item: EvalItem, result: dict[str, Any]) -> EvalRecord:
    raw_contexts = result.get("contexts")
    contexts = normalize_contexts(raw_contexts)
    citations = [_serialize_citation(citation) for citation in (result.get("citations") or [])]
    origins = {
        str(citation.get("origin"))
        for citation in citations
        if citation.get("origin")
    }
    context_source = _context_source(raw_contexts, origins)
    is_stub = context_source == "stub" or origins == {"stub"}
    return EvalRecord(
        item=item,
        answer=str(result.get("answer") or ""),
        contexts=contexts,
        ground_truth=item.golden_answer,
        citations=citations,
        compliance_status=str(result.get("compliance_status") or "unknown"),
        citation_count=len(citations),
        escalated=any(citation.get("origin") == "vision" for citation in citations),
        context_source=context_source,
        is_stub=is_stub,
        # 只反映 workflow 是否用 stub 語料；誠實邊界題合法空 contexts 不等於 smoke。
        is_smoke_test=is_stub,
    )


def _context_text(context: Any) -> str:
    if context is None:
        return ""
    if isinstance(context, str):
        return context.strip()
    if isinstance(context, dict):
        return str(context.get("text") or context.get("page_content") or "").strip()
    for attribute in ("text", "page_content"):
        value = getattr(context, attribute, None)
        if value:
            return str(value).strip()
    return ""


def _context_source(raw_contexts: Any, citation_origins: set[str]) -> str:
    sources: set[str] = set(citation_origins)
    candidates = raw_contexts if isinstance(raw_contexts, list) else [raw_contexts]
    for context in candidates:
        if isinstance(context, dict):
            source = context.get("origin") or context.get("source_type") or context.get("source")
            if source:
                sources.add(str(source))
    if len(sources) == 1:
        return next(iter(sources))
    if sources:
        return "mixed"
    return "unknown"


def _serialize_citation(citation: Any) -> dict[str, Any]:
    if isinstance(citation, dict):
        return dict(citation)
    if hasattr(citation, "model_dump"):
        return citation.model_dump()
    return {
        "source_id": str(getattr(citation, "source_id", "")),
        "snippet": str(getattr(citation, "snippet", "")),
        "origin": str(getattr(citation, "origin", "unknown")),
    }


__all__ = [
    "EvalRecord",
    "normalize_contexts",
    "read_records_jsonl",
    "run_dataset",
    "run_item",
    "write_records_jsonl",
]
