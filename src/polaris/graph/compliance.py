"""Polaris Desk Compliance — NFR-031 買賣建議攔截（純函式）。

對應憲法 Principle I：新聞 / 投研功能**只描述、標證據、標矛盾，
不得產出任何買賣建議**（投顧執照風險）。

W1 D1 用 **substring 黑名單** 做最小攔截，6 條已知關鍵字命中即攔，
回固定安全訊息；不嘗試自動改寫（避免 W1 引入 LLM 成本 + prompt risk）。

R6 W3 將：
- 補完整關鍵字 / regex 集（含同義詞與否定句處理）
- 加紅隊（red-team）對抗測試

本模組設計目標：
- 純字串輸入字串輸出，無外部依賴
- 100% 確定性、單元測試最容易
- 接 LangGraph 節點時只是 wrapper 呼叫（見 stubs.compliance）
"""
from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: W1 D1 攔截關鍵字（spec FR-005 指名的 6 條）。
#: 後續週次（R6 W3）會擴充；增刪須走 PR + 紅隊測試。
BUYSELL_KEYWORDS: tuple[str, ...] = (
    "建議買進",
    "建議賣出",
    "加碼",
    "減碼",
    "看多",
    "看空",
)

#: 攔截後對外輸出的固定訊息。**不可包含 BUYSELL_KEYWORDS 任一**。
SAFE_MESSAGE: str = "本系統不提供買賣建議，僅描述事實與引用來源。"


ComplianceStatus = Literal["passed", "blocked"]


# ---------------------------------------------------------------------------
# Pure function
# ---------------------------------------------------------------------------

def apply_compliance(draft: str) -> tuple[str, ComplianceStatus]:
    """檢查 draft 是否含買賣建議關鍵字。

    Args:
        draft: Writer 節點產出的候選答案字串。

    Returns:
        - ``(SAFE_MESSAGE, "blocked")`` 若 draft 含任一 ``BUYSELL_KEYWORDS``。
        - ``(draft, "passed")`` 否則（原文不變）。

    保證：
        - **回傳的字串中不會包含**任何 ``BUYSELL_KEYWORDS``（SC-003）。
        - 同一 draft 重複呼叫，結果完全相同（無外部 state / 無隨機）。
    """
    if any(kw in draft for kw in BUYSELL_KEYWORDS):
        return SAFE_MESSAGE, "blocked"
    return draft, "passed"


__all__ = [
    "apply_compliance",
    "BUYSELL_KEYWORDS",
    "SAFE_MESSAGE",
    "ComplianceStatus",
]
