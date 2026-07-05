"""R5 Eval 的 Markdown、CSV、JSON、JSONL 與圖表報告。"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from polaris.config import settings
from polaris.eval.runner import EvalRecord, write_records_jsonl
from polaris.eval.score import EvaluationReport, RAGAS_THRESHOLDS

SMOKE_WARNING = "pipeline smoke test，非 G3 真分"


def build_summary(
    records: list[EvalRecord],
    report: EvaluationReport,
) -> dict[str, Any]:
    """彙總總體、各場景、場景 4 固定子集、RAGAS 與合規證據。"""

    record_by_id = {record.item.item_id: record for record in records}
    score_by_id = {score.item_id: score for score in report.scores}
    scenarios: dict[str, list[str]] = defaultdict(list)
    gate_ids: list[str] = []
    for record in records:
        scenarios[record.item.scenario].append(record.item.item_id)
        if record.item.gate_subset == "scenario4_gate":
            gate_ids.append(record.item.item_id)

    failed_cases = []
    for score in report.scores:
        if score.passed:
            continue
        record = record_by_id[score.item_id]
        failed_cases.append(
            {
                "item_id": score.item_id,
                "scenario": record.item.scenario,
                "question": record.item.question,
                "failed_reasons": score.failed_reasons,
                "owner": _failure_owner(score.failed_reasons),
            }
        )

    metric_values: dict[str, list[float]] = defaultdict(list)
    for score in report.scores:
        for metric, value in score.ragas.items():
            # 排除 None（空 contexts）與 nan/inf（judge timeout / RAGAS 放棄該指標）：
            # 一個 nan 會把 mean 毒成 nan，讓聚合報告嚴重低估真實分數。
            if value is not None and math.isfinite(value):
                metric_values[metric].append(value)

    redteam_ids = [record.item.item_id for record in records if record.item.redteam]
    redline_count = sum(
        1
        for item_id in redteam_ids
        if not score_by_id[item_id].checks.get("no_buysell", True)
    )
    visual_records = [record for record in records if record.item.scenario == "3"]
    visual_escalated = sum(1 for record in visual_records if record.escalated)
    return {
        "mode": report.mode,
        "total_cases": len(report.scores),
        "pass_count": sum(score.passed for score in report.scores),
        "pass_rate": report.pass_rate,
        "gate_passed": report.gate_passed,
        "smoke_test": any(record.is_smoke_test for record in records),
        "ragas_averages": {
            metric: mean(values) if values else None
            for metric, values in metric_values.items()
        }
        | {
            metric: None
            for metric in RAGAS_THRESHOLDS
            if metric not in metric_values
        },
        "scenario_results": {
            scenario: _subset_result(item_ids, score_by_id)
            for scenario, item_ids in sorted(scenarios.items())
        },
        "scenario4_gate": _subset_result(gate_ids, score_by_id),
        "redteam": {
            "total": len(redteam_ids),
            "buysell_violations": redline_count,
            "target": 0,
        },
        "compliance_status_counts": dict(
            Counter(record.compliance_status for record in records)
        ),
        "context_count": {
            "min": min((record.context_count for record in records), default=0),
            "max": max((record.context_count for record in records), default=0),
            "average": mean(record.context_count for record in records) if records else 0.0,
        },
        "visual_reader": {
            "total": len(visual_records),
            "escalated": visual_escalated,
            "rate": visual_escalated / len(visual_records) if visual_records else 0.0,
        },
        "failed_cases": failed_cases,
    }


def write_eval_artifacts(
    records: list[EvalRecord],
    report: EvaluationReport,
    *,
    output_dir: str | Path,
    dataset_path: str | Path | None = None,
) -> dict[str, Path]:
    """輸出 G4 所需的報告、明細、原始 records、manifest 與兩張 SVG 圖。"""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = build_summary(records, report)
    paths = {
        "markdown": output / "summary.md",
        "cases_csv": output / "cases.csv",
        "summary_json": output / "summary.json",
        "records_jsonl": output / "records.jsonl",
        "manifest_json": output / "manifest.json",
        "scenario_chart": output / "scenario_pass_rates.svg",
        "ragas_chart": output / "ragas_metrics.svg",
    }
    paths["markdown"].write_text(render_markdown(summary), encoding="utf-8")
    paths["summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_records_jsonl(records, paths["records_jsonl"])
    _write_cases_csv(records, report, paths["cases_csv"])
    paths["manifest_json"].write_text(
        json.dumps(
            _build_manifest(records, report, dataset_path=dataset_path),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_bar_chart(
        paths["scenario_chart"],
        "Scenario pass rate",
        {
            f"Scenario {name}": result["pass_rate"]
            for name, result in summary["scenario_results"].items()
        }
        | {"Scenario 4 gate": summary["scenario4_gate"]["pass_rate"]},
        maximum=1.0,
    )
    _write_bar_chart(
        paths["ragas_chart"],
        "Average RAGAS metrics",
        {
            metric: value or 0.0
            for metric, value in summary["ragas_averages"].items()
        },
        maximum=1.0,
    )
    return paths


def render_markdown(summary: dict[str, Any]) -> str:
    lines = ["# Polaris Desk Eval 報告", ""]
    if summary["smoke_test"]:
        lines.extend([f"> ⚠️ **{SMOKE_WARNING}**", ""])
    lines.extend(
        [
            f"- 模式：`{summary['mode']}`",
            f"- 題數：{summary['total_cases']}",
            f"- 通過：{summary['pass_count']}",
            f"- 達標率：**{summary['pass_rate']:.1%}**（G3 ≥ 80%）",
            f"- G3 gate：**{'PASS' if summary['gate_passed'] else 'FAIL'}**",
            f"- 買賣建議違規：**{summary['redteam']['buysell_violations']}**（目標 = 0）",
            "",
            "## RAGAS",
            "",
        ]
    )
    for metric, threshold in RAGAS_THRESHOLDS.items():
        value = summary["ragas_averages"].get(metric)
        rendered = "n/a" if value is None else f"{value:.3f}"
        lines.append(f"- {metric}: {rendered}（門檻 {threshold:.2f}）")

    lines.extend(["", "## 場景成績", ""])
    for scenario, result in summary["scenario_results"].items():
        lines.append(
            f"- 場景 {scenario}: {result['passed']}/{result['total']} "
            f"({result['pass_rate']:.1%})"
        )
    gate = summary["scenario4_gate"]
    lines.append(
        f"- 場景 4 固定閘門 10 題: {gate['passed']}/{gate['total']} "
        f"({gate['pass_rate']:.1%})"
    )
    visual = summary["visual_reader"]
    if visual["total"]:
        lines.append(
            f"- 場景 3 visual_reader 升級: {visual['escalated']}/{visual['total']} "
            f"({visual['rate']:.1%})"
        )

    lines.extend(["", "## Compliance Status", ""])
    for status, count in sorted(summary["compliance_status_counts"].items()):
        lines.append(f"- {status}: {count}")

    lines.extend(["", "## 不及格清單", ""])
    if not summary["failed_cases"]:
        lines.append("- 無")
    for failed in summary["failed_cases"]:
        lines.append(
            f"- {failed['item_id']}（owner: {failed['owner']}）: "
            + ", ".join(failed["failed_reasons"])
        )
    return "\n".join(lines) + "\n"


def _write_cases_csv(
    records: list[EvalRecord],
    report: EvaluationReport,
    path: Path,
) -> None:
    score_by_id = {score.item_id: score for score in report.scores}
    fields = [
        "item_id", "scenario", "question", "golden_answer", "answer",
        "context_count", "context_source", "compliance_status", "redteam",
        "gate_subset", "context_precision", "faithfulness", "answer_relevancy",
        "judge_passes", "passed", "failed_reasons", "owner",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            score = score_by_id[record.item.item_id]
            writer.writerow(
                {
                    "item_id": record.item.item_id,
                    "scenario": record.item.scenario,
                    "question": record.item.question,
                    "golden_answer": record.ground_truth,
                    "answer": record.answer,
                    "context_count": record.context_count,
                    "context_source": record.context_source,
                    "compliance_status": record.compliance_status,
                    "redteam": record.item.redteam,
                    "gate_subset": record.item.gate_subset,
                    "context_precision": score.ragas.get("context_precision"),
                    "faithfulness": score.ragas.get("faithfulness"),
                    "answer_relevancy": score.ragas.get("answer_relevancy"),
                    "judge_passes": sum(vote.passed for vote in score.judge_votes),
                    "passed": score.passed,
                    "failed_reasons": ";".join(score.failed_reasons),
                    "owner": _failure_owner(score.failed_reasons),
                }
            )


def _build_manifest(
    records: list[EvalRecord],
    report: EvaluationReport,
    *,
    dataset_path: str | Path | None,
) -> dict[str, Any]:
    dataset_hash = None
    if dataset_path is not None and Path(dataset_path).exists():
        dataset_hash = hashlib.sha256(Path(dataset_path).read_bytes()).hexdigest()
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "mode": report.mode,
        "dataset_path": str(dataset_path) if dataset_path else None,
        "dataset_sha256": dataset_hash,
        "record_count": len(records),
        "vector_backend": settings.vector_backend,
        "ragas_judge_model": (
            os.getenv("RAGAS_JUDGE_MODEL")
            or os.getenv("RAGAS_EVALUATOR_MODEL")
        ),
        "judge_models": {
            provider: os.getenv(variable)
            for provider, variable in {
                "gemini": "JUDGE_GEMINI_MODEL",
                "openai": "JUDGE_OPENAI_MODEL",
                "anthropic": "JUDGE_ANTHROPIC_MODEL",
            }.items()
        },
        "contains_stub_records": any(record.is_stub for record in records),
    }


def _subset_result(
    item_ids: list[str],
    score_by_id: dict[str, Any],
) -> dict[str, Any]:
    scores = [score_by_id[item_id] for item_id in item_ids if item_id in score_by_id]
    passed = sum(score.passed for score in scores)
    return {
        "total": len(scores),
        "passed": passed,
        "pass_rate": passed / len(scores) if scores else 0.0,
    }


def _failure_owner(reasons: list[str]) -> str:
    if "no_buysell" in reasons or "compliance_passed" in reasons:
        return "R2"
    if "unscorable_empty_contexts" in reasons or "contexts_nonempty" in reasons:
        return "R3/R4"
    return "R2/R3"


def _write_bar_chart(
    path: Path,
    title: str,
    values: dict[str, float],
    *,
    maximum: float,
) -> None:
    """用標準庫輸出簡單 SVG，讓 token-free smoke 也一定有圖表 artifact。"""

    width = 760
    row_height = 42
    height = 80 + max(1, len(values)) * row_height
    bars = []
    for index, (label, value) in enumerate(values.items()):
        y = 55 + index * row_height
        bar_width = int(480 * max(0.0, min(value / maximum, 1.0)))
        bars.append(
            f'<text x="10" y="{y + 17}" font-size="13">{label}</text>'
            f'<rect x="210" y="{y}" width="{bar_width}" height="22" fill="#167d8d"/>'
            f'<text x="700" y="{y + 17}" font-size="13">{value:.1%}</text>'
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="10" y="28" font-size="20" font-weight="bold">{title}</text>'
        + "".join(bars)
        + "</svg>"
    )
    path.write_text(svg, encoding="utf-8")


__all__ = [
    "SMOKE_WARNING",
    "build_summary",
    "render_markdown",
    "write_eval_artifacts",
]
