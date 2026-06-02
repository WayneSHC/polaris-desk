# API 金鑰設定指南（全員必讀）

> 對應 4 週計畫 **W1 D5 閘門**：「GCP·Gemini key 全隊可用」。
> 金鑰**永遠不進 git**（`.env` 已被 `.gitignore` 忽略）。

## 0. 一句話

每個人在自己機器的 `.env` 填入**自己的** Gemini 金鑰即可；沒填也能跑（節點自動走確定性 fallback，無 LLM）。

## 1. 確認目前狀態

```bash
make check-keys        # 或 python -m polaris doctor
```

會列出每個金鑰是 `✅ set` 還是 `❌ missing`。`❌` 的就是還沒設定。

## 2. 拿一把 Gemini API 金鑰

1. 到 **Google AI Studio**：<https://aistudio.google.com/apikey>
2. 用 Google 帳號登入 → **Create API key**（可掛在免費專案，足夠 W1 開發）。
3. 複製那串 `AIza...` 開頭的金鑰。

## 3. 填進 `.env`

打開 repo 根目錄的 `.env`（沒有的話 `make setup` 會從 `.env.example` 複製一份），把這行：

```dotenv
GEMINI_API_KEY=# 必填（主力模型 Gemini 3.0 Pro/Flash）
```

改成（**去掉 `#`、貼上真金鑰**）：

```dotenv
GEMINI_API_KEY=AIzaSyD....你的金鑰....
```

> ⚠️ 開頭是 `#` 會被視為「未設定」（這是刻意的防呆，避免把註解當金鑰）。

再跑一次 `make check-keys`，應看到 `GEMINI_API_KEY ✅ set`。

## 4. 模型名稱（已預設好，通常不用改）

```dotenv
GEMINI_MODEL_PRO=gemini-3-pro-preview      # 撰寫（Writer）用
GEMINI_MODEL_FLASH=gemini-3-flash-preview  # 規劃（Planner）用，便宜快
EMBEDDING_MODEL=gemini-embedding-2         # 多模態嵌入
```

## 5. 其他金鑰（W2+ 才需要）

| 金鑰 | 用途 | 何時需要 |
|---|---|---|
| `COHERE_API_KEY` | Rerank | W2 檢索 |
| `TAVILY_API_KEY` | 新聞 / Web 檢索 | W2+ |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Eval 3-judge | 閘門評測（R5） |

W1 只需要 `GEMINI_API_KEY`，其餘留空不影響開發。

## 6. 安全守則（憲法 Principle III）

- **金鑰只放 `.env`，永不 commit、不貼進程式碼、不貼進 PR / issue / 聊天室。**
- 上雲後改用 **GCP Secret Manager**（W4），程式照樣從環境變數讀，不改碼。
- 不小心把金鑰推上 GitHub → 立刻到 AI Studio **撤銷重發**，再清 git 歷史。
