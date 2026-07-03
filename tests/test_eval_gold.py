"""Gold set 評測測試（檢索/生成分離 + 失敗分類）。

全程 token=0：檢索用注入的假 retriever，生成用注入的 run_fn。
真 retriever / LLM 不在單測跑（無金鑰時誠實缺席，另有 gated 真資料 smoke）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from polaris.eval.gold import GoldItem, load_gold_set, snapshot_rows
from polaris.eval.gold_report import render_gold_markdown
from polaris.eval.gold_score import GenResult, numeric_match, run_generation, taxonomy
from polaris.eval.gold_score import score_item as score_gen
from polaris.eval.retrieval import run_retrieval, summarize
from polaris.eval.retrieval import score_item as score_retrieval
from polaris.vectorstore.base import SearchResult

GOLD = (
    Path(__file__).resolve().parents[1]
    / "src" / "polaris" / "eval" / "data" / "gold_eps_2026Q1_v1.csv"
)


# ── 假 retriever（注入；SearchResult.id == chunk_id）─────────────────────────
class FakeRetriever:
    """依 chunk_id→排名 腳本回結果，pre/post 可不同以測 rerank_delta。

    ``retrieve()`` 預設把結果標成 rerank 已跑（``origin=="rerank"``，模擬 Cohere 成功）；
    ``rerank_ran=False`` 則保留 bm25 origin，模擬 429/降級 → harness 應報 rerank_delta=None。
    """

    def __init__(self, pre: list[str], post: list[str], rerank_ran: bool = True):
        self._pre, self._post, self._rerank_ran = pre, post, rerank_ran

    def _mk(self, ids, origin):
        return [
            SearchResult(id=c, content="x", score=1.0 - i * 0.01, metadata={"origin": origin})
            for i, c in enumerate(ids)
        ]

    def retrieve_candidates(self, query, *, filters=None, top_k=None):
        return self._mk(self._pre[: (top_k or len(self._pre))], "bm25")

    def retrieve(self, query, *, filters=None):
        return self._mk(self._post, "rerank" if self._rerank_ran else "bm25")


def gold(**kw) -> GoldItem:
    base = dict(item_id="E001", question="台積電 2026Q1 EPS?", metric_id="eps",
                exact_number=22.08, unit="新台幣元/股",
                must_cite_chunk_id=("2330-2026Q1-p004-c002",), answerable="Y",
                corpus_snapshot="2026-07-03 / 10795 rows")
    base.update(kw)
    return GoldItem(**base)


# ── gold 載入 ────────────────────────────────────────────────────────────────
class TestGoldLoader:
    def test_loads_repo_gold(self):
        items = load_gold_set(GOLD)
        assert len(items) == 14                       # EPS 薄切片 14 檔
        assert all(isinstance(i, GoldItem) for i in items)
        assert all(i.metric_id == "eps" for i in items)

    def test_exact_number_parsed_as_float(self):
        tsmc = next(i for i in load_gold_set(GOLD) if "2330" in i.question)
        assert tsmc.exact_number == 22.08

    def test_multi_candidate_chunks_split_on_semicolon(self):
        multi = next(i for i in load_gold_set(GOLD) if len(i.must_cite_chunk_id) > 1)
        assert all(c for c in multi.must_cite_chunk_id)

    def test_answerable_gap_marked(self):
        """華碩(2357) EPS 文字語料查無 → answerable='?'、無 gold chunk。"""
        asus = next(i for i in load_gold_set(GOLD) if "2357" in i.question)
        assert asus.answerable == "?"
        assert asus.must_cite_chunk_id == ()

    def test_company_ticker_parsed(self):
        tsmc = next(i for i in load_gold_set(GOLD) if i.item_id == "E005")
        assert tsmc.company == "2330"

    def test_snapshot_rows_extracted(self):
        assert snapshot_rows(gold()) == 10795

    def test_missing_column_raises(self, tmp_path):
        bad = tmp_path / "bad.csv"
        bad.write_text("item_id,question\nE1,q\n", encoding="utf-8")
        with pytest.raises(ValueError, match="缺欄位"):
            load_gold_set(bad)

    def test_illegal_answerable_raises(self, tmp_path):
        bad = tmp_path / "bad.csv"
        bad.write_text(
            "item_id,question,metric_id,exact_number,must_cite_chunk_id,answerable\n"
            "E1,q,eps,1.0,c1,MAYBE\n", encoding="utf-8")
        with pytest.raises(ValueError, match="answerable"):
            load_gold_set(bad)


# ── 檢索指標 ─────────────────────────────────────────────────────────────────
class TestRetrieval:
    def test_hit_and_recall_when_gold_retrieved(self):
        g = gold()
        r = FakeRetriever(pre=["x", g.must_cite_chunk_id[0], "y"],
                          post=[g.must_cite_chunk_id[0], "x", "y"])
        rec = score_retrieval(g, r)
        assert rec.hit_post[5] is True
        assert rec.recall_post[5] == 1.0
        assert rec.mrr_post == 1.0            # gold 排第一

    def test_rerank_delta_positive_when_pushed_up(self):
        g = gold()
        gid = g.must_cite_chunk_id[0]
        # pre：gold 在第 3；post：rerank 推到第 1 → delta = 3-1 = +2
        r = FakeRetriever(pre=["a", "b", gid], post=[gid, "a", "b"])
        rec = score_retrieval(g, r)
        assert rec.rerank_delta == 2

    def test_rerank_delta_negative_when_buried(self):
        g = gold()
        gid = g.must_cite_chunk_id[0]
        r = FakeRetriever(pre=[gid, "a", "b"], post=["a", "b", gid])
        rec = score_retrieval(g, r)
        assert rec.rerank_delta == -2

    def test_miss_yields_zero_recall(self):
        g = gold()
        r = FakeRetriever(pre=["a", "b"], post=["a", "b"])
        rec = score_retrieval(g, r)
        assert rec.recall_post[10] == 0.0
        assert rec.mrr_post == 0.0
        assert rec.rerank_delta is None       # 兩側皆沒中 → N/A，不編故事

    def test_rerank_ran_detected_from_origin(self):
        g = gold()
        gid = g.must_cite_chunk_id[0]
        rec = score_retrieval(g, FakeRetriever(pre=[gid], post=[gid]))
        assert rec.rerank_ran is True

    def test_rerank_delta_na_when_rerank_did_not_run(self):
        """429/降級：post 未帶 rerank origin → rerank_ran False、delta=None（即使排名有變）。"""
        g = gold()
        gid = g.must_cite_chunk_id[0]
        # pre gold 在第 3、post 在第 1；但 rerank 沒真的跑 → 不得謊報 +2。
        r = FakeRetriever(pre=["a", "b", gid], post=[gid, "a", "b"], rerank_ran=False)
        rec = score_retrieval(g, r)
        assert rec.rerank_ran is False
        assert rec.rerank_delta is None

    def test_summarize_excludes_absent_rerank_from_delta(self):
        g = gold()
        gid = g.must_cite_chunk_id[0]
        ran = score_retrieval(g, FakeRetriever(pre=["a", gid], post=[gid, "a"]))       # delta=+1
        absent = score_retrieval(g, FakeRetriever(pre=["a", gid], post=[gid, "a"], rerank_ran=False))
        s = summarize([ran, absent])
        assert s.n_rerank_ran == 1            # 只有真的跑 rerank 的那題入分母
        assert s.rerank_improved == 1

    def test_no_retriever_is_honest_absence(self):
        rec = score_retrieval(gold(), None)
        assert rec.retriever_available is False
        assert rec.recall_post == {}

    def test_run_retrieval_none_active_in_ci(self, monkeypatch):
        """無 active_retriever（CI/無金鑰）→ 全題誠實缺席。

        強制 active_retriever()→None（別依賴環境剛好沒 ADC/金鑰——有 creds 的機器上
        它會真的建 retriever，測試就漂）。
        """
        monkeypatch.setattr("polaris.retrieval.retriever.active_retriever", lambda: None)
        items = load_gold_set(GOLD)[:3]
        recs = run_retrieval(items)          # retriever=None → active_retriever()
        assert all(not r.retriever_available for r in recs)

    def test_company_filter_forwards_ticker(self):
        """company_filter=True → 每題把 {'company': ticker} 併入 retriever filters。"""
        seen = {}

        class SpyRetriever(FakeRetriever):
            def retrieve_candidates(self, query, *, filters=None, top_k=None):
                seen["cand"] = filters
                return super().retrieve_candidates(query, filters=filters, top_k=top_k)

            def retrieve(self, query, *, filters=None):
                seen["ret"] = filters
                return super().retrieve(query, filters=filters)

        g = gold(company="2330")
        run_retrieval([g], retriever=SpyRetriever(pre=[], post=[]), company_filter=True)
        assert seen["cand"] == {"company": "2330"}
        assert seen["ret"] == {"company": "2330"}

    def test_no_company_filter_by_default(self):
        seen = {}

        class SpyRetriever(FakeRetriever):
            def retrieve(self, query, *, filters=None):
                seen["ret"] = filters
                return super().retrieve(query, filters=filters)

        run_retrieval([gold(company="2330")], retriever=SpyRetriever(pre=[], post=[]))
        assert seen["ret"] is None            # 預設不帶 filter

    def test_summarize_excludes_unanswerable(self):
        g_ok = gold(item_id="E1")
        g_gap = gold(item_id="E2", answerable="?", must_cite_chunk_id=())
        gid = g_ok.must_cite_chunk_id[0]
        r = FakeRetriever(pre=[gid], post=[gid])
        recs = [score_retrieval(g_ok, r), score_retrieval(g_gap, r)]
        s = summarize(recs)
        assert s.n_scored == 1               # answerable='?' 不入分母


# ── 生成指標 + 失敗分類 ──────────────────────────────────────────────────────
class TestNumericMatch:
    def test_eps_exact_two_decimals(self):
        assert numeric_match("每股盈餘為 22.08 元", 22.08, "新台幣元/股")
        assert not numeric_match("每股盈餘為 22.05 元", 22.08, "新台幣元/股")

    def test_percent_tolerance(self):
        assert numeric_match("毛利率約 66.2%", 66.25, "%")     # ±0.1
        assert not numeric_match("毛利率約 60%", 66.25, "%")

    def test_thousands_comma_number(self):
        assert numeric_match("淨利 572,480 千元", 572480.0)

    def test_none_gt_never_matches(self):
        assert not numeric_match("任何 123", None)


class TestGenTaxonomy:
    def _retr(self, g, hit: bool):
        gid = g.must_cite_chunk_id[0] if g.must_cite_chunk_id else "gid"
        ids = [gid] if hit else ["other"]
        return score_retrieval(g, FakeRetriever(pre=ids, post=ids))

    def test_ok_when_number_and_grounded(self):
        g = gold()
        gen = GenResult(answer="EPS 為 22.08 元", citation_ids=g.must_cite_chunk_id)
        s = score_gen(g, gen, self._retr(g, hit=True))
        assert s.bucket == "ok"
        assert s.numeric_ok and s.grounded

    def test_wrong_number_when_retrieved_but_wrong(self):
        g = gold()
        gen = GenResult(answer="EPS 為 19.00 元", citation_ids=g.must_cite_chunk_id)
        s = score_gen(g, gen, self._retr(g, hit=True))
        assert s.bucket == "wrong_number"

    def test_retrieval_miss_when_gold_not_retrieved(self):
        g = gold()
        gen = GenResult(answer="EPS 為 19.00 元")
        s = score_gen(g, gen, self._retr(g, hit=False))
        assert s.bucket == "retrieval_miss"

    def test_ungrounded_when_number_right_but_off_gold_citation(self):
        g = gold()
        gen = GenResult(answer="EPS 為 22.08 元", citation_ids=("some-other-chunk",))
        s = score_gen(g, gen, self._retr(g, hit=True))
        assert s.bucket == "ungrounded?"

    def test_over_hedge_when_answerable_but_hedged(self):
        g = gold()
        gen = GenResult(answer="資料不足，無法回答")
        s = score_gen(g, gen, self._retr(g, hit=True))
        assert s.bucket == "over_hedge"

    def test_unanswerable_ok_when_gap_and_hedged(self):
        g = gold(answerable="?", must_cite_chunk_id=())
        gen = GenResult(answer="資料不足")
        s = score_gen(g, gen, None)
        assert s.bucket == "unanswerable_ok"

    def test_answered_uncertain_when_gap_but_answered(self):
        g = gold(answerable="?", must_cite_chunk_id=())
        gen = GenResult(answer="EPS 大概是 13 元")
        s = score_gen(g, gen, None)
        assert s.bucket == "answered_uncertain"

    def test_run_generation_with_injected_fn(self):
        items = load_gold_set(GOLD)[:2]

        def fake_fn(it):
            return GenResult(answer=f"{it.exact_number}", citation_ids=it.must_cite_chunk_id)

        scores = run_generation(items, run_fn=fake_fn)
        assert len(scores) == 2
        tax = taxonomy(scores)
        assert sum(len(v) for v in tax.values()) == 2


# ── 報告 ─────────────────────────────────────────────────────────────────────
class TestReport:
    def test_absence_note_when_no_retriever(self, monkeypatch):
        monkeypatch.setattr("polaris.retrieval.retriever.active_retriever", lambda: None)
        items = load_gold_set(GOLD)[:3]
        recs = run_retrieval(items)          # 缺席
        md = render_gold_markdown(items, recs)
        assert "檢索缺席" in md

    def test_snapshot_drift_warning(self, monkeypatch):
        monkeypatch.setattr("polaris.retrieval.retriever.active_retriever", lambda: None)
        items = load_gold_set(GOLD)[:1]
        recs = run_retrieval(items)
        md = render_gold_markdown(items, recs, live_corpus_rows=99999)
        assert "語料快照漂移" in md

    def test_report_has_failure_taxonomy(self):
        g = gold()
        gen = GenResult(answer="EPS 為 22.08 元", citation_ids=g.must_cite_chunk_id)
        recs = [score_retrieval(g, FakeRetriever(pre=g.must_cite_chunk_id, post=g.must_cite_chunk_id))]
        scores = [score_gen(g, gen, recs[0])]
        md = render_gold_markdown([g], recs, scores)
        assert "失敗分類" in md and "檢索分" in md
