"""gold set 評測報告（Markdown；檢索分 + 失敗分類）。"""
from __future__ import annotations

from polaris.eval.gold import GoldItem, snapshot_rows
from polaris.eval.gold_score import GoldScore, taxonomy
from polaris.eval.retrieval import DEFAULT_KS, RetrievalRecord, summarize

#: 失敗桶 → 該修的層（報告用；ok/unanswerable_ok 為正常，不算失敗）。
_BUCKET_LAYER = {
    "retrieval_miss": "檢索/rerank",
    "wrong_number": "生成/prompt",
    "ungrounded?": "引用綁定（軟訊號）",
    "over_hedge": "過度保守",
    "answered_uncertain": "待人審（answerable=?）",
}


def render_gold_markdown(
    items: list[GoldItem],
    retrieval: list[RetrievalRecord],
    scores: list[GoldScore] | None = None,
    *,
    ks: tuple[int, ...] = DEFAULT_KS,
    live_corpus_rows: int | None = None,
    mode: str = "",
) -> str:
    lines = ["# Polaris Desk Gold Eval 報告", ""]
    if mode:
        lines += [f"檢索模式：{mode}", ""]

    # 快照守門：gold 釘的 row 數 vs 現況，對不上警告 chunk_id 可能失效。
    snap = next((snapshot_rows(i) for i in items if snapshot_rows(i)), None)
    if snap and live_corpus_rows and snap != live_corpus_rows:
        lines += [
            f"> ⚠️ **語料快照漂移**：gold 釘 {snap} rows，現況 {live_corpus_rows} rows"
            "——must_cite_chunk_id 可能已失效，建議重標。",
            "",
        ]

    s = summarize(retrieval, ks=ks)
    if s.n_skipped_unavailable and s.n_scored == 0:
        lines += [
            "> ℹ️ **檢索缺席**（無 active_retriever / CI 無金鑰）——檢索分略過，非 0 分。",
            "",
        ]
    else:
        lines += ["## 檢索分（token=0；只計 answerable=Y 且有 gold）", ""]
        lines.append(f"- 計分題數：{s.n_scored}（缺席 {s.n_skipped_unavailable}）")
        lines.append("- hit@k (post-rerank)：" + "、".join(f"@{k} {s.hit_post[k]:.0%}" for k in ks))
        lines.append(
            "- recall@k：" + "、".join(
                f"@{k} pre {s.recall_pre[k]:.2f}→post {s.recall_post[k]:.2f}" for k in ks
            )
        )
        lines.append(f"- MRR (post)：{s.mrr_post:.3f}")
        verdict = "值得" if s.rerank_improved > s.rerank_hurt else ("有害" if s.rerank_hurt > s.rerank_improved else "中性")
        lines.append(f"- rerank 影響：推前 {s.rerank_improved} 題 / 埋掉 {s.rerank_hurt} 題 → **{verdict}**")
        lines.append("")

    # answerable 拆分（避免用語料覆蓋率冒充系統品質）。
    n_y = sum(1 for i in items if i.answerable == "Y")
    n_q = sum(1 for i in items if i.answerable == "?")
    n_yq = sum(1 for i in items if i.answerable == "Y?")
    lines += [
        "## Answerable 拆分",
        f"- 明確可答 Y：{n_y}　待確認 Y?：{n_yq}　語料查無 ?：{n_q}",
        "",
    ]

    if scores:
        n_ok = sum(1 for x in scores if x.bucket == "ok")
        n_num = sum(1 for x in scores if x.numeric_ok)
        lines += [
            "## 生成分（token=0 後檢查）",
            f"- 數字正確：{n_num}/{len(scores)}",
            f"- 完全通過（數字對 + 引用接地）：{n_ok}/{len(scores)}",
            "",
            "## 失敗分類（定位該修哪層）",
        ]
        tax = taxonomy(scores)
        for bucket in ["retrieval_miss", "wrong_number", "ungrounded?", "over_hedge",
                       "answered_uncertain", "unanswerable_ok", "ok"]:
            ids = tax.get(bucket, [])
            if not ids:
                continue
            layer = _BUCKET_LAYER.get(bucket, "—")
            tag = "✅" if bucket in ("ok", "unanswerable_ok") else "🔧"
            lines.append(f"- {tag} **{bucket}**（{layer}）：{len(ids)} 題 — {', '.join(ids)}")
        lines.append("")

    return "\n".join(lines)


__all__ = ["render_gold_markdown"]
