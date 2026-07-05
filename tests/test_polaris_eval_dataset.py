from __future__ import annotations

from pathlib import Path

import pytest

from polaris.eval.dataset import load_dataset

DATASET = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "polaris"
    / "eval"
    / "data"
    / "questions_v1.csv"
)


def test_official_dataset_has_130_unique_cases_and_fixed_scenario4_gate():
    items = load_dataset(DATASET, expected_count=130, required_gate_count=10)

    assert len({item.item_id for item in items}) == 130
    assert len({item.question for item in items}) == 130
    gate_items = [item for item in items if item.gate_subset == "scenario4_gate"]
    assert len(gate_items) == 10
    assert all(item.scenario == "4" for item in gate_items)
    assert all(item.golden_answer for item in items)


def test_dataset_loader_accepts_english_aliases(tmp_path):
    path = tmp_path / "english.csv"
    path.write_text(
        "id,scenario,question,ground_truth,company,period,category,is_red_team,gate_subset\n"
        "E1,4,Question?,Answer,TSMC,2025Q1,filing,false,scenario4_gate\n",
        encoding="utf-8",
    )

    item = load_dataset(path)[0]

    assert item.item_id == "E1"
    assert item.golden_answer == "Answer"
    assert item.redteam is False
    assert item.gate_subset == "scenario4_gate"


def test_dataset_rejects_invalid_redteam_value(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(
        "題號,場景,問題,golden_answer,公司,季別,類別,是否紅隊\n"
        "Q1,1,問題,答案,公司,2025Q1,類別,maybe\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="是否紅隊值無效"):
        load_dataset(path)


def test_dataset_rejects_empty_redteam_value(tmp_path):
    path = tmp_path / "empty_redteam.csv"
    path.write_text(
        "題號,場景,問題,golden_answer,公司,季別,類別,是否紅隊\n"
        "Q1,1,問題,答案,公司,2025Q1,類別,\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="是否紅隊值無效"):
        load_dataset(path)
