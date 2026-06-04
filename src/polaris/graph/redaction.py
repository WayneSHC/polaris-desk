"""Polaris Desk — 輸出端機密 / PII 遮罩（純函式，defense-in-depth）。

★ 這是「擋洩漏」那一層，與 graph/compliance.py 的「擋買賣建議」並列。★

設計同 :func:`polaris.graph.compliance.apply_compliance`：純字串輸入字串輸出、
100% 確定性、token-free、零外部依賴；接 LangGraph 節點時只是 wrapper 呼叫
（見 :func:`polaris.graph.nodes.stubs.compliance`）。

⚠️ 範圍與限界（務必理解）：
- 這是**最後一道網（defense-in-depth），不是主防線**。secrets 的根本解法是
  「永遠不要把金鑰 / 憑證放進模型的 prompt / context」（輸入端衛生）。注入攻擊可
  叫模型把機密拆字 / 編碼以繞過正則 —— 故本層僅降低風險、不保證攔截。
- **MNPI（重大未公開資訊）不在此層**：MNPI 不是 pattern，無法用正則辨識；它是
  存取控制問題，須在 ingestion 標記 + 檢索層（owner / confidential filter）擋。
- 刻意**保守**：只比對高辨識度的格式，避免把正常財務數字 / source_id 誤刪而傷接地。
"""
from __future__ import annotations

import re

#: (label, compiled pattern)。順序：先比對前綴明確的金鑰，再 email / 身分證 / 手機。
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GOOGLE_API_KEY", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("OPENAI_API_KEY", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("TW_ID", re.compile(r"\b[A-Z][12]\d{8}\b")),       # 台灣身分證字號
    ("TW_MOBILE", re.compile(r"\b09\d{8}\b")),          # 台灣手機號
)


def redact(text: str) -> tuple[str, list[str]]:
    """遮罩 text 內的機密 / PII。

    Returns:
        ``(redacted_text, hit_labels)``。命中處換成 ``[REDACTED:<label>]``；
        無命中時回原文與空清單。同一輸入重複呼叫結果相同（無 state / 無隨機）。
    """
    if not text:
        return text, []
    hits: list[str] = []
    out = text
    for label, pattern in _PATTERNS:
        def _sub(_m: re.Match[str], _label: str = label) -> str:
            hits.append(_label)
            return f"[REDACTED:{_label}]"
        out = pattern.sub(_sub, out)
    return out, hits


__all__ = ["redact"]
