"""Gemini 用戶端薄封裝（@R2 / @R3）。

使用新版 **google-genai** SDK（`pip install google-genai`），
取代已淘汰的舊 `google-generativeai`。API 形態：
    from google import genai
    client = genai.Client(api_key=...)
    client.models.generate_content(model=..., contents=...)

LLM 本就走雲端 API，本地 / 雲端共用此封裝。金鑰從 settings（.env）讀。
重相依採延遲 import，未安裝 SDK 時 `import polaris` 仍正常。
"""
from __future__ import annotations

from ..config import settings


def is_real_key(key: str | None) -> bool:
    """金鑰是否「真的設定了」。

    `.env` 佔位字串是 ``'# 必填…'``——truthy 但無效。空字串 / 純空白 /
    `#` 開頭（註解佔位）一律視為未設定，避免下游以為有金鑰、卻在呼叫時才爆。
    """
    if not key:
        return False
    stripped = key.strip()
    return bool(stripped) and not stripped.startswith("#")


def available() -> bool:
    """目前 settings 內是否有可用的 Gemini 金鑰。"""
    return is_real_key(settings.gemini_api_key)


def active_llm() -> "GeminiClient | None":
    """有真金鑰 → 回 GeminiClient；否則回 None（呼叫端走確定性 fallback）。

    無金鑰時**不**建立 client、不觸發 google-genai import，CI / 無金鑰開發
    皆可正常跑（憲法成本紀律）。
    """
    return GeminiClient() if available() else None


class GeminiClient:
    def __init__(self) -> None:
        if not is_real_key(settings.gemini_api_key):
            raise RuntimeError("缺少有效 GEMINI_API_KEY，請在 .env 填入真實金鑰")
        from google import genai  # 延遲 import
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def generate(
        self,
        prompt: str,
        *,
        flash: bool = False,
        system_instruction: str | None = None,
    ) -> str:
        """單輪文字生成。flash=True 用便宜快速的 Flash 模型。"""
        from google.genai import types  # 延遲 import

        model = settings.gemini_model_flash if flash else settings.gemini_model_pro
        config = (
            types.GenerateContentConfig(system_instruction=system_instruction)
            if system_instruction
            else None
        )
        resp = self._client.models.generate_content(
            model=model, contents=prompt, config=config
        )
        return resp.text

    def embed(self, text: str) -> list[float]:
        """產生 embedding（入庫與查詢都用）；維度由 .env EMBEDDING_DIM 控制。

        TODO(@R4)：W1 接 DB 後，確認回傳形狀與 batch 寫法（可一次 contents=[...] 多筆）。
        """
        from google.genai import types  # 延遲 import

        resp = self._client.models.embed_content(
            model=settings.embedding_model,
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=settings.embedding_dim),
        )
        return list(resp.embeddings[0].values)
