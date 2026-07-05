"""R5 Eval 題庫載入與契約驗證。

CSV 可使用開工指南的中文欄頭或等價英文欄頭；進入 pipeline 後一律轉成
凍結的 :class:`EvalItem`，避免 runner、score、report 各自猜測欄位名稱。
"""
from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

_ALIASES: dict[str, tuple[str, ...]] = {
    "item_id": ("題號", "id", "item_id"),
    "scenario": ("場景", "scenario"),
    "question": ("問題", "question"),
    "golden_answer": ("golden_answer", "ground_truth"),
    "company": ("公司", "company"),
    "period": ("季別", "period"),
    "category": ("類別", "category"),
    "redteam": ("是否紅隊", "is_red_team", "redteam"),
    "gate_subset": ("gate_subset", "閘門子集"),
}
_REQUIRED = {
    "item_id",
    "scenario",
    "question",
    "golden_answer",
    "company",
    "period",
    "category",
    "redteam",
}
_TRUE_VALUES = {"Y", "YES", "TRUE", "1", "是"}
# 「是否紅隊」為 _REQUIRED 必填且決定套用哪組合規檢查，空值不可靜默降級成
# 非紅隊（合規風險），須讓 _parse_bool raise。故意不含 ""。
_FALSE_VALUES = {"N", "NO", "FALSE", "0", "否"}


class EvalItem(BaseModel):
    """單一正式評測題。"""

    model_config = ConfigDict(frozen=True)

    item_id: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    question: str = Field(min_length=1)
    golden_answer: str = Field(min_length=1)
    company: str = ""
    period: str = ""
    category: str = ""
    redteam: bool = False
    gate_subset: str = ""


def load_dataset(
    path: str | Path,
    *,
    expected_count: int | None = None,
    required_gate_count: int | None = None,
) -> list[EvalItem]:
    """讀取 CSV 並驗證 ID、問題、golden answer 與固定閘門子集。"""

    csv_path = Path(path)
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = [
            canonical
            for canonical in sorted(_REQUIRED)
            if not any(alias in fieldnames for alias in _ALIASES[canonical])
        ]
        if missing:
            raise ValueError(f"題庫缺欄位：{missing}")

        items = [_normalize_row(row, row_number=index) for index, row in enumerate(reader, 2)]

    validate_dataset(
        items,
        path=csv_path,
        expected_count=expected_count,
        required_gate_count=required_gate_count,
    )
    return items


def validate_dataset(
    items: list[EvalItem],
    *,
    path: str | Path = "<memory>",
    expected_count: int | None = None,
    required_gate_count: int | None = None,
) -> None:
    """驗證正式題庫不可出現空題庫、重複題或錯誤場景 4 閘門標記。"""

    if not items:
        raise ValueError(f"題庫為空：{path}")
    if expected_count is not None and len(items) != expected_count:
        raise ValueError(f"題庫題數應為 {expected_count}，實際為 {len(items)}")

    ids = [item.item_id for item in items]
    questions = [item.question for item in items]
    duplicate_ids = _duplicates(ids)
    duplicate_questions = _duplicates(questions)
    if duplicate_ids:
        raise ValueError(f"題號重複：{duplicate_ids}")
    if duplicate_questions:
        raise ValueError(f"問題重複：{duplicate_questions}")

    gate_items = [item for item in items if item.gate_subset == "scenario4_gate"]
    if required_gate_count is not None and len(gate_items) != required_gate_count:
        raise ValueError(
            f"scenario4_gate 應為 {required_gate_count} 題，實際為 {len(gate_items)}"
        )
    invalid_gate = [item.item_id for item in gate_items if item.scenario != "4"]
    if invalid_gate:
        raise ValueError(f"scenario4_gate 只能包含場景 4：{invalid_gate}")


def _normalize_row(row: dict[str, str], *, row_number: int) -> EvalItem:
    data = {
        canonical: _read_alias(row, aliases)
        for canonical, aliases in _ALIASES.items()
    }
    data["redteam"] = _parse_bool(data["redteam"], row_number=row_number)
    try:
        return EvalItem(**data)
    except ValueError as exc:
        raise ValueError(f"題庫第 {row_number} 列格式錯誤：{exc}") from exc


def _read_alias(row: dict[str, str], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        if alias in row:
            return (row.get(alias) or "").strip()
    return ""


def _parse_bool(value: str, *, row_number: int) -> bool:
    normalized = value.strip().upper()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"題庫第 {row_number} 列是否紅隊值無效：{value!r}")


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


__all__ = ["EvalItem", "load_dataset", "validate_dataset"]
