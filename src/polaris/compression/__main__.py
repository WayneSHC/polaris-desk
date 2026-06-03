"""POC runner：``python -m polaris.compression``（D8）。

對代表性語料跑壓縮量測並印報告。預設走確定性壓縮器（token-free）；
本機要量 LLMLingua ≥50% 目標時設 ``POLARIS_USE_LLMLINGUA=1`` 並裝
``polaris-desk[llmlingua]`` 後重跑，數字回填設計文件 §6。
"""
from __future__ import annotations

from typing import Any

from polaris.compression.compressors import active_compressor
from polaris.compression.measure import format_report, measure_contexts

#: 與 W2 D6 retriever stub 語料同形（每季一筆，含 boilerplate 前綴）。
_STUB_CORPUS: list[dict[str, Any]] = [
    {
        "source_id": f"stub-2330-{q}",
        "text": f"（v0 stub）台積電 {q} 法說摘要：營收與毛利率資料。",
    }
    for q in ("2024Q1", "2024Q2", "2024Q3", "2024Q4", "2025Q1")
]

#: 較長、較冗的代表性中文財經片段（含重複句 / boilerplate / 多餘空白）。
_REALISTIC_CORPUS: list[dict[str, Any]] = [
    {
        "source_id": "law-meeting-2025Q1",
        "text": (
            "（v0 stub）台積電 2025 年第一季法人說明會表示，"
            "本季合併營收約新台幣 8,390 億元，季減約 5%、年增約 35%。\n"
            "（v0 stub）台積電 2025 年第一季法人說明會表示，"  # 重複行
            "本季合併營收約新台幣 8,390 億元，季減約 5%、年增約 35%。\n"
            "毛利率   約   58.8%   ，   營業利益率   約   48.5%   。"  # 多餘空白
        ),
    },
    {
        "source_id": "mops-2025Q1",
        "text": (
            "（v0 stub）公開資訊觀測站重大訊息：本公司於 2025 年第一季"
            "資本支出約 100 億美元，先進製程（3 奈米 / 5 奈米）需求強勁。"
        ),
    },
]

_CORPORA: dict[str, list[dict[str, Any]]] = {
    "D6 stub 語料": _STUB_CORPUS,
    "代表性較長片段": _REALISTIC_CORPUS,
}


def build_report() -> str:
    """對各語料跑 :func:`measure_contexts` 並組出多區段報告字串。"""
    compressor = active_compressor()
    header = f"=== Polaris Desk · D8 LLMLingua POC（壓縮器：{compressor.name}）==="
    sections = [header]
    for name, contexts in _CORPORA.items():
        result = measure_contexts(contexts, compressor=compressor)
        sections.append(f"# {name}\n{format_report(result)}")
    return "\n\n".join(sections)


def main() -> None:
    print(build_report())


if __name__ == "__main__":
    main()
