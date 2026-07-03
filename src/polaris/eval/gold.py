"""加料 gold set 載入（檢索 / 生成分離評測用）。

有別於 :mod:`polaris.eval.dataset`（散文 golden_answer、跑 smoke/Ragas），本 gold set
每題帶**可驗證的錨點**——精確數字 + 必引 chunk_id + 可回答旗標——供三支確定性指標共用：

- 檢索 recall@k（:mod:`polaris.eval.retrieval`）：``must_cite_chunk_id`` 當 relevant set。
- 數字正確性（:mod:`polaris.eval.gold_score`）：``exact_number`` 當 GT。
- 引用-支持（同上）：系統引用是否 ∈ ``must_cite_chunk_id``。

CSV 欄（``utf-8-sig`` 開檔吞 BOM）：
``item_id, question, metric_id, exact_number, unit, must_cite_chunk_id, answerable, corpus_snapshot``

- ``must_cite_chunk_id``：``;`` 分隔（人審前可為多個候選；審後通常收斂為 1）。
- ``answerable``：``Y``（語料撐得起）/ ``?``（文字語料查無 → 可能結構化-only，須人審）/
  ``Y?``（僅新聞/逐字稿候選、待確認）。**分數要按此拆開看**，否則量的是語料覆蓋率而非系統品質。
- ``corpus_snapshot``：釘住產製當下的語料快照（日期 / row 數）；chunk_id 是內容錨點，
  語料 re-ingest 後可能失效 → harness 跑前應校驗（見 :func:`snapshot_rows`）。
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

#: CSV 必要欄頭（缺即拋——gold 檔格式是契約）。
_REQUIRED = {
    "item_id",
    "question",
    "metric_id",
    "exact_number",
    "must_cite_chunk_id",
    "answerable",
}

_ANSWERABLE = {"Y", "Y?", "?"}


class GoldItem(BaseModel):
    """單一 gold 題：帶可驗證錨點。"""

    model_config = ConfigDict(frozen=True)

    item_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    metric_id: str = Field(default="")
    exact_number: float | None = None
    unit: str = Field(default="")
    #: ticker（如 '2330'）；供 company-filter 模式帶 ``filters={'company': ...}``。
    company: str = Field(default="")
    #: 必引 chunk_id 集合（relevant set）；空 = 尚無文字候選（answerable='?'）。
    must_cite_chunk_id: tuple[str, ...] = ()
    answerable: str = Field(default="Y")
    corpus_snapshot: str = Field(default="")

    @property
    def is_answerable(self) -> bool:
        """明確可答（Y）；``?`` / ``Y?`` 皆非確定可答，分數另計。"""
        return self.answerable == "Y"


def snapshot_rows(item: GoldItem) -> int | None:
    """從 ``corpus_snapshot`` 抽 row 數（如 ``'2026-07-03 / 10795 rows'`` → 10795）。

    供 harness 跑前校驗語料快照是否漂移；抽不出回 ``None``。
    """
    m = re.search(r"(\d[\d,]*)\s*rows", item.corpus_snapshot)
    return int(m.group(1).replace(",", "")) if m else None


def load_gold_set(path: str | Path) -> list[GoldItem]:
    """讀 gold CSV → ``list[GoldItem]``；缺必要欄頭或空檔即拋。"""
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = set(reader.fieldnames or [])
        missing = _REQUIRED - fields
        if missing:
            raise ValueError(f"gold 檔缺欄位：{sorted(missing)}")
        items: list[GoldItem] = []
        for row in reader:
            raw_num = (row.get("exact_number") or "").strip()
            chunks = tuple(
                c.strip()
                for c in (row.get("must_cite_chunk_id") or "").split(";")
                if c.strip()
            )
            answerable = (row.get("answerable") or "Y").strip() or "Y"
            if answerable not in _ANSWERABLE:
                raise ValueError(
                    f"{row.get('item_id')}: answerable 非法值 {answerable!r}（限 {_ANSWERABLE}）"
                )
            items.append(
                GoldItem(
                    item_id=(row.get("item_id") or "").strip(),
                    question=(row.get("question") or "").strip(),
                    metric_id=(row.get("metric_id") or "").strip(),
                    exact_number=float(raw_num) if raw_num else None,
                    unit=(row.get("unit") or "").strip(),
                    company=(row.get("company") or "").strip(),
                    must_cite_chunk_id=chunks,
                    answerable=answerable,
                    corpus_snapshot=(row.get("corpus_snapshot") or "").strip(),
                )
            )
    if not items:
        raise ValueError(f"gold 檔為空：{path}")
    return items


__all__ = ["GoldItem", "load_gold_set", "snapshot_rows"]
