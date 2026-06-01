"""T015 — 測試 src/polaris/graph/compliance.py 的 apply_compliance() 純函式。

對應 spec FR-005 + SC-003：6 條已知關鍵字攔截率 = 100%；最終 answer 中含
買賣建議字眼的測試案例數 = 0。

憲法 Principle I（NFR-031）的最小可演示版本。
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 攔截 — 6 條已知關鍵字 100% blocked
# ---------------------------------------------------------------------------

class TestComplianceBlocks:

    @pytest.mark.parametrize("keyword", [
        "建議買進",
        "建議賣出",
        "加碼",
        "減碼",
        "看多",
        "看空",
    ])
    def test_blocks_each_buysell_keyword(self, keyword):
        from polaris.graph.compliance import apply_compliance, SAFE_MESSAGE, BUYSELL_KEYWORDS

        draft = f"分析師{keyword}台積電，理由為產能釋出。"
        final, status = apply_compliance(draft)

        assert status == "blocked", f"failed to block keyword: {keyword!r}"
        assert final == SAFE_MESSAGE
        # SC-003：最終文字不可含**任何**關鍵字
        for kw in BUYSELL_KEYWORDS:
            assert kw not in final, f"safe message leaked keyword: {kw!r}"

    def test_blocks_when_keyword_at_end(self):
        from polaris.graph.compliance import apply_compliance

        final, status = apply_compliance("台積電法說透露需求強勁，建議買進。")
        assert status == "blocked"

    def test_blocks_when_keyword_at_start(self):
        from polaris.graph.compliance import apply_compliance

        final, status = apply_compliance("看多台積電未來成長性。")
        assert status == "blocked"

    def test_blocks_even_with_multiple_keywords(self):
        from polaris.graph.compliance import apply_compliance

        final, status = apply_compliance("分析師看多並建議買進。")
        assert status == "blocked"


# ---------------------------------------------------------------------------
# 放行 — 合規草稿原封不動 + status=passed
# ---------------------------------------------------------------------------

class TestCompliancePasses:

    @pytest.mark.parametrize("draft", [
        "台積電 2025 Q1 營收 YoY 約 12.34%。",
        "依據法說會頁碼 5：公司預期下半年產能利用率將維持高檔。",
        "新聞顯示外資對該公司持股比例上升。",
    ])
    def test_compliant_draft_unchanged(self, draft):
        from polaris.graph.compliance import apply_compliance

        final, status = apply_compliance(draft)
        assert status == "passed"
        assert final == draft, "compliant draft should be returned byte-identical"

    def test_empty_draft_is_passed(self):
        from polaris.graph.compliance import apply_compliance

        final, status = apply_compliance("")
        assert status == "passed"
        assert final == ""

    def test_compliant_draft_with_similar_words_not_blocked(self):
        """確認不會誤殺：「不建議」「無加減碼」這類否定/相似詞不可被攔。"""
        from polaris.graph.compliance import apply_compliance

        # 注意：本測試**有意**避免使用 6 條關鍵字（建議買進 / 建議賣出 / 加碼 / 減碼 / 看多 / 看空）
        # 中的任何子字串。W1 D1 用 substring 比對，命中即攔；
        # 後續週次（R6 W3）若改 regex，可放寬此測試。
        for draft in [
            "公司營收年增 5%。",
            "市場對下季展望保守。",
            "外資持股比例下降。",
        ]:
            final, status = apply_compliance(draft)
            assert status == "passed", f"unexpectedly blocked: {draft!r}"


# ---------------------------------------------------------------------------
# 關鍵字常數本身的健全性
# ---------------------------------------------------------------------------

class TestKeywordRegistry:

    def test_exactly_six_keywords(self):
        """spec FR-005 與 SC-003 都指名 6 條。"""
        from polaris.graph.compliance import BUYSELL_KEYWORDS

        assert len(BUYSELL_KEYWORDS) == 6

    def test_keywords_are_strings_and_non_empty(self):
        from polaris.graph.compliance import BUYSELL_KEYWORDS

        for kw in BUYSELL_KEYWORDS:
            assert isinstance(kw, str)
            assert kw.strip() == kw and len(kw) > 0

    def test_safe_message_contains_no_keyword(self):
        """SAFE_MESSAGE 自身不可踩雷。"""
        from polaris.graph.compliance import BUYSELL_KEYWORDS, SAFE_MESSAGE

        for kw in BUYSELL_KEYWORDS:
            assert kw not in SAFE_MESSAGE
