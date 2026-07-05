"""R5 Eval CLI and report integration tests."""
from __future__ import annotations

import json

from polaris.eval.__main__ import main
from polaris.eval.dataset import EvalItem
from polaris.eval.report import build_summary, write_eval_artifacts
from polaris.eval.runner import EvalRecord
from polaris.eval.score import score_records


def make_record(
    item_id: str,
    scenario: str = "1",
    gate_subset: str = "",
    *,
    escalated: bool = False,
) -> EvalRecord:
    item = EvalItem(
        item_id=item_id,
        scenario=scenario,
        question=f"question {item_id}",
        golden_answer="ground truth",
        gate_subset=gate_subset,
    )
    origin = "vision" if escalated else "stub"
    return EvalRecord(
        item=item,
        answer="answer",
        contexts=["context"],
        ground_truth=item.golden_answer,
        citations=[{"source_id": "s", "snippet": "context", "origin": origin}],
        compliance_status="passed",
        citation_count=1,
        escalated=escalated,
        context_source=origin,
        is_stub=origin == "stub",
        is_smoke_test=True,
    )


def test_report_writes_all_artifacts(tmp_path):
    records = [
        make_record("Q1"),
        make_record("Q2", scenario="4", gate_subset="scenario4_gate"),
    ]
    report = score_records(records, mode="smoke")

    paths = write_eval_artifacts(records, report, output_dir=tmp_path)
    summary = build_summary(records, report)

    assert all(path.exists() for path in paths.values())
    assert summary["scenario4_gate"]["total"] == 1
    assert summary["redteam"]["buysell_violations"] == 0
    assert "pipeline smoke test" in paths["markdown"].read_text(encoding="utf-8")
    assert json.loads(paths["summary_json"].read_text(encoding="utf-8"))["total_cases"] == 2


def test_cli_reuse_records_does_not_run_workflow(tmp_path, monkeypatch):
    records = [make_record("Q1")]
    records_path = write_eval_artifacts(
        records,
        score_records(records, mode="smoke"),
        output_dir=tmp_path / "source",
    )["records_jsonl"]
    monkeypatch.setattr(
        "polaris.eval.__main__.run_dataset",
        lambda items: (_ for _ in ()).throw(AssertionError("workflow should not run")),
    )

    exit_code = main(
        [
            "--mode",
            "smoke",
            "--reuse-records",
            str(records_path),
            "--output-dir",
            str(tmp_path / "rerun"),
        ]
    )

    assert exit_code == 0


def test_report_tracks_visual_reader_escalation(tmp_path):
    records = [
        make_record("V1", scenario="3", escalated=True),
        make_record("V2", scenario="3", escalated=False),
    ]
    report = score_records(records, mode="smoke")

    paths = write_eval_artifacts(records, report, output_dir=tmp_path)
    summary = build_summary(records, report)
    markdown = paths["markdown"].read_text(encoding="utf-8")

    assert summary["visual_reader"]["escalated"] == 1
    assert summary["visual_reader"]["total"] == 2
    assert "visual_reader" in markdown
    assert "1/2" in markdown


def test_summary_ragas_average_ignores_nan():
    """單一 nan（judge timeout / RAGAS 放棄一個指標）不得毒化整組平均。"""
    import math

    from polaris.eval.score import CaseScore, EvaluationReport

    records = [make_record("Q1"), make_record("Q2")]
    report = EvaluationReport(
        mode="flash",
        scores=[
            CaseScore(
                item_id="Q1",
                checks={},
                ragas={"faithfulness": 1.0, "context_precision": 0.9, "answer_relevancy": 0.9},
            ),
            CaseScore(
                item_id="Q2",
                checks={},
                ragas={"faithfulness": float("nan"), "context_precision": 0.8, "answer_relevancy": 0.8},
            ),
        ],
    )

    averages = build_summary(records, report)["ragas_averages"]

    # Q2 的 faithfulness=nan 應被排除 → 平均只算 Q1 = 1.0，而非被毒成 nan
    assert averages["faithfulness"] == 1.0
    assert math.isclose(averages["context_precision"], 0.85)
