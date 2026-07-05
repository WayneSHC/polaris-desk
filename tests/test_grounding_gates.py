"""Tests for is_traceable_prose + numbers_grounded (Task 1 — grounding gate pure functions)."""
from __future__ import annotations


from polaris.graph.deep_research import state as st
from polaris.graph.state import Citation


def _c(sid: str, snip: str = "片段") -> Citation:
    return Citation(source_id=sid, snippet=snip, origin="stub")


# ---------------------------------------------------------------------------
# is_traceable_prose
# ---------------------------------------------------------------------------


class TestIsTraceableProse:
    def test_valid_full_width_tag(self):
        ev = [_c("s1")]
        assert st.is_traceable_prose("台積電毛利率 55%（來源：s1）", ev) is True

    def test_multiple_valid_tags(self):
        ev = [_c("s1"), _c("s2")]
        assert st.is_traceable_prose("A（來源：s1）且 B（來源：s2）", ev) is True

    def test_no_tag_returns_false(self):
        ev = [_c("s1")]
        assert st.is_traceable_prose("台積電毛利率 55%，沒有來源", ev) is False

    def test_sid_not_in_evidence_returns_false(self):
        ev = [_c("s1")]
        assert st.is_traceable_prose("台積電（來源：s99）", ev) is False

    def test_at_least_one_valid_tag_is_enough(self):
        """prose 可有部分無效 tag，只要 ≥1 個有效即 pass。"""
        ev = [_c("s1")]
        assert st.is_traceable_prose("A（來源：s1）B（來源：s99）", ev) is True

    def test_half_width_parenthesis_normalized(self):
        """(來源：sid) 半形括號也需能被接受。"""
        ev = [_c("s1")]
        assert st.is_traceable_prose("台積電(來源：s1)", ev) is True

    def test_half_width_colon_normalized(self):
        """R2：Flash 常輸出半形冒號 `(來源:sid)`；若不收 → 閘門永遠 fail → 靜默退回 base。"""
        ev = [_c("s1")]
        assert st.is_traceable_prose("台積電(來源:s1)", ev) is True
        assert st.is_traceable_prose("台積電（來源:s1）", ev) is True

    def test_empty_text_returns_false(self):
        ev = [_c("s1")]
        assert st.is_traceable_prose("", ev) is False

    def test_empty_evidence_returns_false(self):
        assert st.is_traceable_prose("A（來源：s1）", []) is False


# ---------------------------------------------------------------------------
# numbers_grounded
# ---------------------------------------------------------------------------


class TestNumbersGrounded:
    def test_no_numbers_in_prose_returns_true(self):
        ev = [_c("s1", "無數字")]
        assert st.numbers_grounded("台積電毛利率穩定（來源：s1）", ev) is True

    def test_number_present_in_evidence_returns_true(self):
        ev = [_c("s1", "毛利率 55.4%")]
        assert st.numbers_grounded("毛利率 55.4%（來源：s1）", ev) is True

    def test_number_absent_from_evidence_returns_false(self):
        ev = [_c("s1", "毛利率 50%")]
        assert st.numbers_grounded("毛利率 99%（來源：s1）", ev) is False

    def test_sid_number_not_counted_in_evidence(self):
        """stub-2330 的 2330 不應被視為有效 evidence 數字。"""
        ev = [_c("stub-2330", "本季毛利率穩定，無具體數字")]
        # prose 含 2330，但 evidence snippet 不包含 2330（只有 sid 帶它）
        assert st.numbers_grounded("公司代碼 2330（來源：stub-2330）", ev) is False

    def test_sid_number_in_snippet_is_valid(self):
        """snippet 明確含數字則有效。"""
        ev = [_c("stub-2330", "股票代碼 2330 本季表現")]
        assert st.numbers_grounded("公司代碼 2330（來源：stub-2330）", ev) is True

    def test_percentage_number_extracted(self):
        ev = [_c("s1", "毛利率 12.3%")]
        assert st.numbers_grounded("毛利率 12.3%（來源：s1）", ev) is True

    def test_source_tag_numbers_excluded_from_prose(self):
        """來源 tag 裡的數字不應被計入 prose 需驗證的數字。"""
        ev = [_c("s99", "無數字片段")]
        # （來源：s99）裡的 99 不算 prose 數字，prose 本身無數字 → True
        assert st.numbers_grounded("台積電表現良好（來源：s99）", ev) is True

    def test_multiple_numbers_all_must_be_grounded(self):
        ev = [_c("s1", "毛利率 55% 營收 100 億")]
        assert st.numbers_grounded("毛利率 55% 營收 100 億（來源：s1）", ev) is True

    def test_partial_numbers_ungrounded_returns_false(self):
        ev = [_c("s1", "毛利率 55%")]
        # 55 grounded but 999 is not
        assert st.numbers_grounded("毛利率 55%，目標 999 億（來源：s1）", ev) is False

    def test_empty_evidence_with_numbers_returns_false(self):
        assert st.numbers_grounded("毛利率 55%", []) is False

    def test_empty_evidence_no_numbers_returns_true(self):
        assert st.numbers_grounded("無數字", []) is True


# ---------------------------------------------------------------------------
# numbers_grounded_in_text — text-vs-text gate (P1 peer-compare)
# ---------------------------------------------------------------------------


class TestNumbersGroundedInText:
    BASE = "台積電毛利率 58.8%，聯電毛利率 47.9%（來源：s1）"

    def test_direct_subset_passes(self):
        assert st.numbers_grounded_in_text("台積電 58.8%（來源：s1）", self.BASE) is True

    def test_no_numbers_passes(self):
        assert st.numbers_grounded_in_text("兩家表現分歧（來源：s1）", self.BASE) is True

    def test_derived_number_blocked_by_default(self):
        # #56：預設嚴格子集 —— 派生數字 10.9 不在 base → 擋（backward-compat）。
        prose = "台積電毛利率高出 10.9 個百分點（來源：s1）"
        assert st.numbers_grounded_in_text(prose, self.BASE) is False

    # --- allow_arithmetic (#56 Option A) ---

    def test_correct_difference_allowed(self):
        # 58.8 − 47.9 = 10.9，重算相等 → 放行。
        prose = "台積電毛利率高出 10.9 個百分點（來源：s1）"
        assert st.numbers_grounded_in_text(prose, self.BASE, allow_arithmetic=True) is True

    def test_correct_sum_allowed(self):
        base = "A 為 30，B 為 12（來源：s1）"
        assert st.numbers_grounded_in_text("兩者合計 42（來源：s1）", base, allow_arithmetic=True) is True

    def test_wrong_arithmetic_blocked(self):
        # Flash 算錯：58.8 − 47.9 = 10.9，但寫成 10.8 → 精確不等 → 擋。
        prose = "台積電毛利率高出 10.8 個百分點（來源：s1）"
        assert st.numbers_grounded_in_text(prose, self.BASE, allow_arithmetic=True) is False

    def test_non_base_number_blocked_even_with_arithmetic(self):
        # 999 既不在 base、也非任兩 base 數字的 ± → 擋。
        prose = "神秘目標 999（來源：s1）"
        assert st.numbers_grounded_in_text(prose, self.BASE, allow_arithmetic=True) is False

    def test_multiplication_not_allowed(self):
        # 乘除不放行：3 × 4 = 12 不得過閘（只允許 ±）。
        base = "數量 3，單位 4（來源：s1）"
        assert st.numbers_grounded_in_text("推導 12（來源：s1）", base, allow_arithmetic=True) is False

    def test_single_base_number_not_self_derivable(self):
        # 只有一個 base 數字時，不得靠自己湊出派生數字（需兩個相異 base 數字）。
        base = "唯一數字 50（來源：s1）"
        assert st.numbers_grounded_in_text("推導 100（來源：s1）", base, allow_arithmetic=True) is False
