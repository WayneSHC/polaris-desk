"""編排層的純邏輯：依內容 md5 去重、同 (period,lang) 流水號。"""
from __future__ import annotations

from ec_model import Doc
from fetch_earnings_call import assign_filenames, dedupe_by_content, merge_by_key


def _doc(period="2026Q1", lang="zh", url="u1", date="2026-05-19"):
    return Doc("2891", "中信金控", "presentation", period, lang, date,
               "source_listing", url, "p")


def test_dedupe_drops_identical_bytes():
    a, b = _doc(url="u1"), _doc(url="u2")           # 不同 URL、相同內容
    blobs = {"u1": b"PDFDATA", "u2": b"PDFDATA"}
    kept = dedupe_by_content([a, b], blobs)
    assert len(kept) == 1


def test_dedupe_keeps_distinct_bytes():
    a, b = _doc(url="u1"), _doc(url="u2")
    blobs = {"u1": b"AAA", "u2": b"BBB"}
    assert len(dedupe_by_content([a, b], blobs)) == 2


def test_assign_filenames_sequences_same_period_lang():
    a, b = _doc(url="u1"), _doc(url="u2")
    blobs = {"u1": b"AAA", "u2": b"BBB"}
    named = assign_filenames([a, b], blobs)
    names = sorted(n for _, n in named)
    assert names[0].endswith("M01_2026Q1_concall_presentation.pdf")
    assert names[1].endswith("M02_2026Q1_concall_presentation.pdf")


def test_assign_filenames_separates_lang_sequence():
    zh, en = _doc(lang="zh", url="u1"), _doc(lang="en", url="u2")
    blobs = {"u1": b"AAA", "u2": b"BBB"}
    named = dict((d.source_url, n) for d, n in assign_filenames([zh, en], blobs))
    assert "M01" in named["u1"]
    assert "E01" in named["u2"]


def test_merge_by_key_collapses_same_period_lang_doctype():
    # 兩個來源給同季同語言、但 URL/內容不同 → 只留先到者（adapter 優先）
    a = _doc(period="2026Q1", lang="zh", url="todayir")   # 先到＝adapter
    b = _doc(period="2026Q1", lang="zh", url="mops")
    merged = merge_by_key([a, b])
    assert len(merged) == 1
    assert merged[0].source_url == "todayir"


def test_merge_by_key_keeps_distinct_lang_and_period():
    zh = _doc(period="2026Q1", lang="zh", url="u1")
    en = _doc(period="2026Q1", lang="en", url="u2")
    q2 = _doc(period="2025Q4", lang="zh", url="u3")
    merged = merge_by_key([zh, en, q2])
    assert len(merged) == 3
