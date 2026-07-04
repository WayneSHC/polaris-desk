from __future__ import annotations

from types import SimpleNamespace

from polaris.eval.dataset import EvalItem
from polaris.eval.runner import (
    EvalRecord,
    normalize_contexts,
    read_records_jsonl,
    run_dataset,
    write_records_jsonl,
)


class EmptyContextApp:
    """真實 workflow 對誠實邊界題合法回空 contexts，但仍是真跑而非 stub。"""

    def invoke(self, payload):
        return {
            "answer": "資料不足",
            "contexts": [],
            "citations": [],
            "compliance_status": "passed",
        }


class FakeApp:
    def __init__(self):
        self.calls = 0

    def invoke(self, payload):
        self.calls += 1
        return {
            "answer": f"answer: {payload['query']}",
            "contexts": [
                {"text": "dict context", "origin": "stub"},
                "string context",
                SimpleNamespace(page_content="object context"),
                None,
            ],
            "citations": [
                {"source_id": "stub-1", "snippet": "dict context", "origin": "stub"}
            ],
            "compliance_status": "passed",
        }


def make_item(item_id: str = "Q1", scenario: str = "1") -> EvalItem:
    return EvalItem(
        item_id=item_id,
        scenario=scenario,
        question=f"question {item_id}",
        golden_answer="ground truth",
    )


def test_normalize_contexts_supports_dict_string_object_and_none():
    contexts = normalize_contexts(
        [
            {"text": "dict"},
            "string",
            SimpleNamespace(text="text attr"),
            SimpleNamespace(page_content="page content"),
            None,
        ]
    )

    assert contexts == ["dict", "string", "text attr", "page content"]
    assert normalize_contexts(None) == []


def test_run_dataset_reuses_injected_workflow_and_marks_stub():
    app = FakeApp()

    records = run_dataset([make_item("Q1"), make_item("Q2")], app=app)

    assert app.calls == 2
    assert records[0].contexts == ["dict context", "string context", "object context"]
    assert records[0].context_count == 3
    assert records[0].is_stub is True
    assert records[0].is_smoke_test is True


def test_run_dataset_builds_workflow_only_once(monkeypatch):
    app = FakeApp()
    builds = 0

    def build():
        nonlocal builds
        builds += 1
        return app

    monkeypatch.setattr("polaris.graph.workflow.build_workflow", build)

    run_dataset([make_item("Q1"), make_item("Q2")])

    assert builds == 1
    assert app.calls == 2


def test_records_jsonl_round_trip(tmp_path):
    records = run_dataset([make_item()], app=FakeApp())
    path = write_records_jsonl(records, tmp_path / "records.jsonl")

    restored = read_records_jsonl(path)

    assert restored[0].to_dict() == records[0].to_dict()


def test_legit_empty_contexts_from_real_workflow_is_not_smoke():
    records = run_dataset([make_item("Q1")], app=EmptyContextApp())

    assert records[0].contexts == []
    assert records[0].is_stub is False
    assert records[0].is_smoke_test is False


def test_from_dict_tolerates_added_and_removed_fields():
    record = run_dataset([make_item("Q1")], app=FakeApp())[0]
    data = record.to_dict()
    data["future_field_added_later"] = "ignore me"
    del data["context_source"]

    restored = EvalRecord.from_dict(data)

    assert restored.item.item_id == "Q1"
    assert restored.context_source == "unknown"
    assert not hasattr(restored, "future_field_added_later")
