"""ec_model 純函式：期別正規化、ROC 日期解析、檔名產生。"""
from __future__ import annotations

from ec_companies import lookup
from ec_model import Doc, build_filename, cn_quarter_num, month_to_quarter, parse_roc_date, to_period


def test_month_to_quarter():
    assert month_to_quarter("03") == 1
    assert month_to_quarter("06") == 2
    assert month_to_quarter("09") == 3
    assert month_to_quarter("12") == 4


def test_cn_quarter_num():
    assert cn_quarter_num("一") == 1
    assert cn_quarter_num("四") == 4


def test_to_period():
    assert to_period(2026, 1) == "2026Q1"
    assert to_period(2024, 4) == "2024Q4"


def test_parse_roc_date_minguo():
    assert parse_roc_date("法人說明會 中華民國115年5月19日 舉行") == "2026-05-19"


def test_parse_roc_date_western():
    assert parse_roc_date("會議日期 2026年5月19日") == "2026-05-19"


def test_parse_roc_date_none():
    assert parse_roc_date("沒有日期的字串") == ""


def test_build_filename_zh_presentation():
    d = Doc(
        stock_id="2891", company="中信金控", doc_type="presentation",
        fiscal_period="2026Q1", lang="zh", event_date="2026-05-19",
        date_source="pdf_first_page", source_url="u", source_page="p",
    )
    assert build_filename(d, 1) == "2891_20260519M001_2026Q1_concall_presentation.pdf"


def test_build_filename_en_transcript_seq2():
    d = Doc(
        stock_id="2330", company="台積電", doc_type="transcript",
        fiscal_period="2025Q4", lang="en", event_date="2026-01-16",
        date_source="source_listing", source_url="u", source_page="p",
    )
    assert build_filename(d, 2) == "2330_20260116E002_2025Q4_concall_transcript.pdf"


def test_build_filename_unknown_date():
    d = Doc(
        stock_id="2891", company="中信金控", doc_type="presentation",
        fiscal_period="2026Q1", lang="zh", event_date="",
        date_source="unknown", source_url="u", source_page="p",
    )
    assert build_filename(d, 1) == "2891_00000000M001_2026Q1_concall_presentation.pdf"


def test_lookup_known_company_ctbc():
    info = lookup("2891")
    assert info is not None
    assert info["name"] == "中信金控"
    assert info["vendor"] == "todayir"
    assert "{year}" in info["page_tmpl"]


def test_lookup_unknown_returns_none():
    assert lookup("9999") is None
