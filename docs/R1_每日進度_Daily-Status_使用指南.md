# R1 PM — 每日進度（Daily Status）使用指南

> 給 R1（郝家銘／施惠棋）。這份說明你「每天怎麼用」這套自動進度，以及怎麼把它接到 Notion。

## 這是什麼

每天**台北早上 07:10**，系統會自動把「昨天大家在 GitHub 上做的事」整理好，你不用追問任何人、任何人也不用手動回報。它從每個人的 GitHub 活動（合併的 PR、開的 PR、code review、關掉的 issue、commit 數）自動歸到 R1–R7，產出兩個東西：

1. **一張滾動更新的 GitHub Issue**：標題「📊 Daily Status (rolling)」—— 你早上看這張就好。
2. **一份 Notion 可匯入的 CSV**：放在 repo 的 `status` 分支 —— 你抓去更新 Notion。

---

## 你每天要做的 3 件事（約 30 秒）

1. **看 Issue**：早上打開「📊 Daily Status (rolling)」這張 Issue，最上面那一天就是昨天的進度表，一眼看完 7 個角色。
2. **抓 CSV**（要進 Notion 時）：到 `status` 分支下載當天的 CSV。
3. **匯進 Notion**：把 CSV 用「Merge with CSV」併進你的進度資料庫。

> 不想每天匯 Notion 也行 —— 光看 Issue 就掌握進度了。CSV 是給你想在 Notion 做累積統計／看板時用的。

---

## 三個地方在哪

**① 滾動 Issue**
`https://github.com/WayneSHC/polaris-desk/issues` → 找標題「📊 Daily Status (rolling)」（有 `daily-status` 標籤）。建議把它 **Pin（釘選）**，每天固定看同一張。

**② status 分支的 CSV**
- 網頁看：`https://github.com/WayneSHC/polaris-desk/tree/status/reports/daily`
- 直接下載某天：`https://raw.githubusercontent.com/WayneSHC/polaris-desk/status/reports/daily/2026-06-02.csv`（把日期換成你要的那天）
- 每天一個檔：`reports/daily/YYYY-MM-DD.md`（人看的）+ `YYYY-MM-DD.csv`（給 Notion）

**③ 匯進 Notion**
1. 在 Notion 打開你的「進度」資料庫（Database）。
2. 右上角 `⋯` →「**Merge with CSV**」（合併 CSV）。
3. 選剛下載的 `YYYY-MM-DD.csv` → 它會把當天 7 列**追加**進資料庫。
4. 連續每天併，Notion 就累積成「角色 × 日期」的進度表，可做篩選、看板、統計。

> CSV 欄名已對齊你們既有的 `01_PM_Notion匯入/*.csv` 風格（中文欄名 + R1–R7）。

---

## 進度表／CSV 欄位怎麼讀

| 欄位 | 意思 |
|---|---|
| 日期 | 報告的那一天（台北時間，昨天） |
| 角色 / 成員 | R1–R7 與姓名 |
| 完成PR | 當天**合併**的 PR（最強的「完成一件事」訊號） |
| 進行中PR | 當天**開啟且還沒合併**的 PR |
| Review數 | 當天給別人 PR 的 review 次數（你們 main 要 1 個 approval，所以 review 也是重要工作） |
| 關閉Issue | 當天關掉的 issue |
| commit數 | 當天 commit 數（輔助參考；因用 squash 合併，以「完成PR」為主） |
| 摘要 | 一句話：合併了哪幾號、開了哪幾號… |

---

## ⚠️ 很重要：它「看不到」什麼（別誤判）

這套是**自動從 GitHub 活動推導**，所以只看得到「有碰到 GitHub 的事」。**看不到**：開會、讀文件做研究、規劃、未經 commit 的手動操作（例如有些 GCP 設定）。

所以：
- **某人今天 0 活動 ≠ 沒做事** —— 他可能在做不經過 GitHub 的工作。把它當「GitHub 上的客觀紀錄」，不是「考勤表」。
- 想讓非程式工作也現身：請那位同事在當天那張 Issue **留一行言**說明即可（這是慣例，系統不強迫）。

---

## 常見狀況處理

**有人出現在「未對應帳號」區塊**
表示有個 GitHub 帳號沒被歸到角色（可能換了帳號、或是 bot）。把那個帳號名字告訴 **R2（施惠棋）**，請他在 `src/polaris/daily_status/roles.py` 補上對應，下次就會自動歸位。

**今天那張 Issue 沒更新 / Actions 紅燈**
到 `https://github.com/WayneSHC/polaris-desk/actions` → 點「daily-status」看哪一步失敗，截圖丟給 R2。最常見原因是 repo 的 Actions 寫入權限沒開（見下方「一次性開通」）。

**想手動補跑某天**
請 R2 在 Actions 頁面對「daily-status」按「Run workflow」（或 `gh workflow run daily-status.yml --ref main`）。

---

## 一次性開通（合併 PR #13 後，做一次就好；建議 R2 操作）

1. **開 Actions 寫入權限**：repo → Settings → Actions → General → **Workflow permissions** → 選「Read and write permissions」→ Save。（否則 Action 發不了 Issue、推不了 status 分支）
2. **先手動觸發一次驗收**：Actions → 「daily-status」→ Run workflow（選 main）。跑完應該會：出現「📊 Daily Status (rolling)」Issue、`status` 分支出現昨天的 md+csv。
3. **試匯 Notion 一次**：下載那份 csv，用「Merge with CSV」併進 Notion 進度庫，確認欄位對得上。

完成後，之後每天 07:10 會自動跑，你只要看 Issue / 抓 CSV。

---

## 之後想更省事？

現在是「Action 產 CSV → 你手動匯 Notion」。未來可升級成 **Action 直接寫進 Notion**（你連 CSV 都不用抓，打開 Notion 就有），只需要一組 Notion integration token + 資料庫 ID。要做時跟工程組說一聲即可（程式已預留這條升級路）。
