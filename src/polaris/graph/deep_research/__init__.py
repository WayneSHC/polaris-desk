"""Deep Research Agent（R2 W3）— 自寫 ReAct loop（AQ-03 決策，見 D11 設計文件）。

- :mod:`polaris.graph.deep_research.react`：ReAct prompt + 工具協定 + action parser（D13）。
- :mod:`polaris.graph.deep_research.state`：ReActStep / dedup_evidence / should_continue（D15）。
- :mod:`polaris.graph.deep_research.agent`：run_deep_research（自寫 ReAct loop，D15）。
"""
from __future__ import annotations

__all__ = ["react", "state", "agent"]
