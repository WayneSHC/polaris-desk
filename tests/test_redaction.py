"""輸出端機密 / PII 遮罩 —— redact 純函式 + compliance 節點整合。"""
from __future__ import annotations

from polaris.graph.redaction import redact

_FAKE_GOOGLE_KEY = "AIza" + "B" * 35  # 符合 AIza + 35 字元的格式（非真金鑰）


def test_redacts_google_api_key():
    out, hits = redact(f"金鑰是 {_FAKE_GOOGLE_KEY} 請保密")
    assert "AIza" not in out
    assert "[REDACTED:GOOGLE_API_KEY]" in out
    assert hits == ["GOOGLE_API_KEY"]


def test_redacts_email_tw_id_and_mobile():
    out, hits = redact("聯絡 jane@example.com，身分證 A123456789，手機 0912345678")
    assert "jane@example.com" not in out
    assert "A123456789" not in out
    assert "0912345678" not in out
    assert set(hits) == {"EMAIL", "TW_ID", "TW_MOBILE"}


def test_passes_through_normal_financial_text():
    """保守設計：正常財務數字 / source_id 不得被誤遮（否則傷接地）。"""
    text = "台積電 2025Q1 營收 5926 億元，YoY 約 12.34%（來源 stub-2330-2025Q1）。"
    out, hits = redact(text)
    assert out == text
    assert hits == []


def test_empty_and_idempotent():
    assert redact("") == ("", [])
    once, _ = redact("mail a@b.co")
    assert "[REDACTED:EMAIL]" in once
    twice, hits2 = redact(once)
    assert twice == once and hits2 == []   # 遮罩後再跑不應再改動


def test_compliance_node_redacts_output():
    """整合：機密 / PII 經 compliance 節點後不得出現在最終 answer。"""
    from unittest.mock import patch

    from polaris.graph.nodes import stubs
    from polaris.graph.nodes.trace import traced
    from polaris.graph.workflow import build_workflow

    leaky = f"聯絡 ir@acme.com，金鑰 {_FAKE_GOOGLE_KEY}，客戶身分證 A123456789。"

    @traced("writer")
    def _leaky_writer(state):
        return {"draft": leaky, "citations": []}

    with patch.object(stubs, "writer", _leaky_writer):
        res = build_workflow().invoke({"query": "處理客戶資料"})

    ans = res.get("answer", "")
    assert "ir@acme.com" not in ans
    assert "AIza" not in ans
    assert "A123456789" not in ans
    assert res.get("compliance_status") == "passed"  # 非買賣建議 → 放行但已遮罩
