from __future__ import annotations

from polaris.eval.dataset import EvalItem
from polaris.eval.judges import JudgeVote
from polaris.eval.runner import EvalRecord
from polaris.eval.score import RAGAS_THRESHOLDS, _env_positive_int, ragas_score, score_records


def make_record(*, contexts: list[str] | None = None) -> EvalRecord:
    item = EvalItem(
        item_id="Q1",
        scenario="1",
        question="question",
        golden_answer="ground truth",
    )
    return EvalRecord(
        item=item,
        answer="grounded answer",
        contexts=["context"] if contexts is None else contexts,
        ground_truth=item.golden_answer,
        citations=[{"source_id": "s1", "snippet": "context", "origin": "embedding"}],
        compliance_status="passed",
        context_source="embedding",
    )


def test_smoke_mode_does_not_call_ragas():
    def fail(_records):
        raise AssertionError("RAGAS must not run in smoke mode")

    report = score_records([make_record()], mode="smoke", ragas_evaluator=fail)

    assert report.scores[0].passed is True


def test_ragas_maps_per_case_scores_and_threshold_boundaries():
    values = dict(RAGAS_THRESHOLDS)
    report = score_records(
        [make_record()],
        mode="flash",
        ragas_evaluator=lambda records: [values],
    )

    assert report.scores[0].ragas == values
    assert report.scores[0].passed is True


def test_ragas_nan_is_a_fail_closed_score():
    report = score_records(
        [make_record()],
        mode="flash",
        ragas_evaluator=lambda records: [
            {
                "context_precision": float("nan"),
                "faithfulness": 1.0,
                "answer_relevancy": 1.0,
            }
        ],
    )

    assert report.scores[0].passed is False
    assert "context_precision_below_0.85" in report.scores[0].failed_reasons


def test_ragas_runtime_limit_uses_safe_positive_default(monkeypatch):
    monkeypatch.setenv("RAGAS_MAX_WORKERS", "0")
    assert _env_positive_int("RAGAS_MAX_WORKERS", 4) == 4

    monkeypatch.setenv("RAGAS_MAX_WORKERS", "3")
    assert _env_positive_int("RAGAS_MAX_WORKERS", 4) == 3


def test_empty_contexts_are_unscorable_and_not_sent_to_ragas():
    record = make_record(contexts=[])
    called = False

    def evaluator(_records):
        nonlocal called
        called = True
        return []

    scores = ragas_score([record], evaluator=evaluator)
    report = score_records([record], mode="flash", ragas_evaluator=evaluator)

    assert called is False
    assert scores["Q1"]["faithfulness"] is None
    assert report.scores[0].scorable is False
    assert "unscorable_empty_contexts" in report.scores[0].failed_reasons


SAFE_ANSWER = "本系統不提供買賣建議，僅描述事實與引用來源。"


def make_special_record(
    *,
    category: str,
    redteam: bool,
    answer: str,
    contexts: list[str],
    citations: list[dict] | None = None,
) -> EvalRecord:
    item = EvalItem(
        item_id="Q1",
        scenario="1",
        question="question",
        golden_answer="ground truth",
        category=category,
        redteam=redteam,
    )
    return EvalRecord(
        item=item,
        answer=answer,
        contexts=contexts,
        ground_truth=item.golden_answer,
        citations=[] if citations is None else citations,
        compliance_status="passed",
        context_source="unknown",
    )


def test_redteam_empty_contexts_not_penalized_by_ragas_in_flash():
    record = make_special_record(
        category="紅隊", redteam=True, answer=SAFE_ANSWER, contexts=[]
    )

    report = score_records(
        [record], mode="flash", ragas_evaluator=lambda records: []
    )

    score = report.scores[0]
    assert score.scorable is True
    assert "unscorable_empty_contexts" not in score.failed_reasons
    assert not any(reason.startswith(tuple(RAGAS_THRESHOLDS)) for reason in score.failed_reasons)
    assert score.passed is True


def test_honest_boundary_empty_contexts_not_penalized_by_ragas_in_flash():
    record = make_special_record(
        category="誠實邊界",
        redteam=False,
        answer="2023Q4 資料不足，無法回答。",
        contexts=[],
    )

    report = score_records(
        [record], mode="flash", ragas_evaluator=lambda records: []
    )

    score = report.scores[0]
    assert score.scorable is True
    assert "unscorable_empty_contexts" not in score.failed_reasons
    assert score.passed is True


def test_redteam_empty_contexts_pass_in_gate_when_judges_pass(monkeypatch):
    record = make_special_record(
        category="紅隊", redteam=True, answer=SAFE_ANSWER, contexts=[]
    )
    monkeypatch.setattr(
        "polaris.eval.score.judge_records",
        lambda records, clients=None: {
            "Q1": [
                JudgeVote("gemini", "g", True, "ok"),
                JudgeVote("openai", "o", True, "ok"),
                JudgeVote("anthropic", "a", True, "ok"),
            ]
        },
    )

    report = score_records(
        [record],
        mode="gate",
        ragas_evaluator=lambda records: [],
        judge_clients={},
    )

    score = report.scores[0]
    assert "unscorable_empty_contexts" not in score.failed_reasons
    assert score.passed is True


def test_general_empty_contexts_still_unscorable_after_fix():
    record = make_special_record(
        category="財務基本", redteam=False, answer="有內容", contexts=[]
    )

    report = score_records(
        [record], mode="flash", ragas_evaluator=lambda records: []
    )

    score = report.scores[0]
    assert score.scorable is False
    assert "unscorable_empty_contexts" in score.failed_reasons
    assert score.passed is False


def test_gate_requires_two_of_three_judges(monkeypatch):
    votes = [
        JudgeVote("gemini", "g", True, "ok"),
        JudgeVote("openai", "o", True, "ok"),
        JudgeVote("anthropic", "a", False, "not enough"),
    ]
    monkeypatch.setattr(
        "polaris.eval.score.judge_records",
        lambda records, clients=None: {"Q1": votes},
    )

    report = score_records(
        [make_record()],
        mode="gate",
        ragas_evaluator=lambda records: [dict(RAGAS_THRESHOLDS)],
        judge_clients={},
    )

    assert report.scores[0].passed is True
