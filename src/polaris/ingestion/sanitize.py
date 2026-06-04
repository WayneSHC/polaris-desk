"""Ingestion 端文件淨化 / 驗證（LLM04 資料投毒 + LLM01 間接注入的源頭防線）。

R4 在把法說稿 / 新聞 / 財報切塊入庫（embedding + 寫 vector store）**之前**，先過
這層：移除可被當成隱藏指令的結構（HTML 註解、零寬 / BiDi / 控制字元），並驗證
基本欄位與長度上限。純函式、確定性、零外部依賴、易單測。

這是**源頭防線**，與 #33（prompt 層把檢索內容當不可信資料）互補：
- 入庫淨化 = 不讓投毒內容進到語料；
- prompt 硬化 = 萬一進來了，模型也不把它當指令。

⚠️ 限界：這層處理「結構性隱藏指令」（如 ``<!-- SYSTEM: ... -->``、零寬 / BiDi 字元），
**不做語意判斷**（要不要因內容可疑而 quarantine 由 R4 / R6 政策決定）。
"""
from __future__ import annotations

import re
import unicodedata

#: 入庫單塊內容字數上限（防超長投毒塊；可依語料調整）。
MAX_CONTENT_CHARS = 20_000

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def sanitize_text(text: str) -> str:
    """移除 HTML 註解、控制 / 格式字元（含零寬 / BiDi），保留換行與 tab。

    零寬空格、BiDi override、BOM 等 Unicode category 皆為 'Cf'，連同 'Cc' 控制字元
    一併以 category 開頭為 'C' 過濾（換行 \\n、tab \\t 例外保留）。
    """
    if not text:
        return ""
    out = _HTML_COMMENT.sub("", text)
    out = "".join(
        ch for ch in out
        if ch in ("\n", "\t") or unicodedata.category(ch)[0] != "C"
    )
    return out.strip()


def validate_for_ingestion(
    doc_id: str, content: str, *, max_chars: int = MAX_CONTENT_CHARS
) -> list[str]:
    """回傳問題清單（空 = 通過）。R4 可據此 reject / quarantine 該塊。"""
    issues: list[str] = []
    if not (doc_id and doc_id.strip()):
        issues.append("empty id")
    if not (content and content.strip()):
        issues.append("empty content")
    if len(content) > max_chars:
        issues.append(f"content too long ({len(content)} > {max_chars})")
    return issues


__all__ = ["MAX_CONTENT_CHARS", "sanitize_text", "validate_for_ingestion"]
