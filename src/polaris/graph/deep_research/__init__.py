"""Deep Research Agent（R2 W3）— 自寫 ReAct loop（AQ-03 決策，見 D11 設計文件）。

- :mod:`polaris.graph.deep_research.react`：ReAct prompt + 工具協定 + action parser（D13）。
- 狀態模型（ReActStep / iteration / evidence / should_continue）與 loop 本體於 D15 落地。
"""
from __future__ import annotations

__all__ = ["react"]
