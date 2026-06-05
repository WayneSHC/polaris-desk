# Polaris Desk 技術部落格

對應 R2 spec D19–20。技術內容皆可對照本 repo 原始碼，誠實不浮誇、守 NFR-031。

1. [Workflow 還是 Agent？混合式架構抉擇](01_workflow_vs_agent.md) — workflow vs agent 的區分、為何主路徑用確定性 5 節點 workflow、agent 只進駐開放式問題、共用 Compliance 閘。
2. [自己寫一個 ReAct Agent：Deep Research 設計](02_deep_research_agent.md) — 為何不用 prebuilt（AQ-03）、≤6 迴圈/≥3 引用的硬邊界、verify-or-synthesize 接地、fail-to-deterministic。
