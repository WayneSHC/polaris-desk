# R6 G3 Smoke Test 20 Summary

## 基本資訊

- 測試日期：2026-06-15
- 測試目的：G3 第一輪無 UI Smoke Test
- 測試方法：依 `docs/測試指南_無UI.md`，使用 CLI / API / ask workflow
- 測試範圍：20 題
- 測試紀錄：`R6_G3_Smoke_Test_20.xlsx`

## 測試結果

| 類別 | 結果 |
|---|---:|
| Red Team / NFR-031 | 8 / 8 Pass |
| Company Facts | 4 / 4 Needs Review |
| Reasoning | 4 / 4 Needs Review |
| Earnings Call | 2 / 2 Needs Review |
| News | 2 / 2 Needs Review |
| Total | 8 Pass, 12 Needs Review, 0 Fail |

## 初步結論

1. NFR-031 合規紅線初步通過，未觀察到買賣建議、目標價、資產配置建議、未發布財報數字或明顯 hallucination。
2. 12 題 Needs Review 主要原因是目前回答仍多引用 `stub-2330-2025Q1`，尚未 grounding 到對應公司、法說會、新聞與多來源資料。
3. 真實金融 QA、citation grounding、多來源 reasoning 需等 `polaris_core` / retriever grounding 接上後重測。

## 備註

本輪測試是 G3 smoke validation，不等同於完整金融 QA 驗收。Needs Review 不代表 Fail，而是表示目前系統仍在 stub mode 或尚未接上對應資料來源，需待真資料 grounding 完成後重新驗證。
