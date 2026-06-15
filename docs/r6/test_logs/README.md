# R6 Test Logs

This folder stores R6 Financial Quality Engineer test records for Polaris Desk.

## Files

| File | Purpose |
|---|---|
| `R6_G3_Smoke_Test_20.xlsx` | First-round G3 smoke test execution log covering 20 R6 cases. |
| `R6_G3_Smoke_Test_20_Summary.md` | Human-readable summary of first-round G3 smoke test results. |
| `R6_Test_Log_v0.1.xlsx` | Broader R6 QA test log template for ongoing red-team, citation, hallucination, and financial QA review. |

## Notes

- `R6_G3_Smoke_Test_20.xlsx` is the first-round G3 Smoke Test package.
- Needs Review does not mean Fail. In this round, Needs Review mainly means the current CLI response is still grounded on `stub-2330-2025Q1` and should be retested after real `polaris_core` / retriever grounding is connected.
- Do not commit `.env`, API keys, gcloud credentials, `.venv`, `__pycache__`, or local machine paths.

## R6 Review Focus

- NFR-031: no buy/sell advice, target price, return forecast, or asset allocation advice.
- Citation grounding: financial numbers, earnings-call guidance, news events, and comparison claims must be traceable.
- Hallucination: no fabricated financial numbers, sources, companies, executives, events, or unpublished reports.
- Financial QA: company, ticker, period, metric, and source alignment must be checked before final G3/G4 evidence is considered complete.
