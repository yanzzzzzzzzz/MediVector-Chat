# GitHub issue implementation status — 2026-11-06

## Scope decision — 2026-11-06

目前交付定位暫定為「醫療文件知識管理原型」。工程驗收涵蓋文件／版本／審核流程、角色與範圍權限、引用追溯、檢索及無證據處理；使用合成或經授權的非個人資料，不宣稱醫療內容正確性或臨床安全已驗證。

- 目前工程優先項目：擴充測試語料、重現 PDF 漏檢與不相關候選問題、固定來源與題目比較標題／頁碼／分塊策略，依結果補回歸測試。
- #5 的文件支持性人工核對與 #8 的人工標註正式 baseline 保持未完成；合成工程診斷不能取代這些驗收證據，但不阻擋目前原型工程交付。
- 醫療內容專業審查與 #20 真人訪談／Pilot 屬後續實際導入驗證；沒有參與者時如實保留待辦。
- #9、#10、#12 原有較廣的品質／產品驗收依賴保持開啟，不能因縮小目前交付範圍就宣稱已完成。

以下 open/closed 狀態及歷史紀錄保留原驗收範圍。本次只更新專案文件，未變更 GitHub issue 狀態或人工審查資料。

## Current state

Closed after implementation/acceptance review and passing CI: **#1–#4, #6, #7, #11, #13–#19**.
Implementation commits and test evidence are recorded on each GitHub issue. Latest engineering validation:
88 backend tests (real PostgreSQL, no OpenAI Key), seven frontend tests, lint/TypeScript/build and CI.
The local preview is running; its configured answer model is GPT-6 Luna.

| Open issue | Remaining requirement |
|---|---|
| #5 | Actual human claim/citation-support annotation of prepared real responses; do not turn pending review into Pass |
| #8 | Human review of 30 proposed cases, measured baseline and real failure analysis; independent Lab remote/push/CI is established |
| #9 | Product Epic depends on the remaining reviewed quality and professional Pilot evidence |
| #10 | Source assistant engineering workflow/scope comparison is available; reviewed answer support and baseline still pending |
| #12 | Rules, snapshots, audit and gates are available; reviewed baseline/answer-quality evidence still pending |
| #20 | Actual 3–5 professional interviews and Pilot; protocol/report templates are prepared, no results fabricated |

The independent .NET Lab is a separate checkout, not a platform embedded here. It passes Release build
and synthetic metric/contract self-tests; its private remote is now
https://github.com/yanzzzzzzzzz/rag-evaluation-lab. See human review materials in
`candidates/` and the Pilot kit in `../docs/pilot/`.

## Historical implementation log (2026-11-04 onward)

The following entries record what each increment implemented and which limits applied at that time.
Later increments supersede earlier pending-feature notes; use the current state above for open/closed status.
Issue #8 remains preparation until its real human/baseline requirements are satisfied. The Lab remote
was established on 2026-11-06; earlier entries about the missing remote are historical.

User confirmed that the ground-truth dataset and separate Evaluation Lab have not yet been
established. Issue #8 remains pending dataset creation and human review; the existing template
and exporter are preparation only, not a verified baseline.

| Issue | Implementation and verification | Remaining limits |
|---|---|---|
| [#1](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/1) | Stateless POST /api/retrieval/search, request/response schemas, effective query/config, ranking/timing, local/token authorization; success/empty/error/access tests | No real OpenAI calls were made; embeddings are mocked in integration tests |
| [#2](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/2) | retrieve_candidates/filter_references split, configurable K/candidate/distance/dedup, raw ranks, compatible chat wrapper; boundary/sort/dedup/K tests | Controlled clinical quality comparisons require reviewed corpus labels |
| [#3](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/3) | Legacy and token strategies, overlap, source SHA/version/offsets/PDF page mappings, fresh experiment schema importer, retrieval metadata; DB import/reject-overwrite tests | Opt-in experiment tooling; existing production uploads keep the baseline strategy. No claim of improved Recall without reviewed data |
| [#4](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/4) | Seeded synthetic corpus/query script, Exact/HNSW plans, Recall@K/P50/P95/serial QPS, environment and table/index footprint; executed against isolated pgvector container | Small warm-cache synthetic test, not production capacity or clinical quality; peak RAM and concurrent load not measured |
| [#5](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/5) | UI labels retrieval heuristic explicitly; citation failure fixtures and annotation-based scorer separate generation/retrieval results; tests cover all fixture cases | Semantic support requires human annotation; fixtures are illustrative and not independently reviewed medical examples |
| [#6](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/6) | Bounded transient retries, exponential backoff/jitter, Retry-After, absolute cancellable deadline, sanitized structured diagnostics; mock status/network/deadline tests | Deadline is per external call, not the entire multi-call question workflow |
| [#7](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/7) | All APIs protected, per-principal schemas, admin document mutations, front-end Token input, bounded body size/rate, local Docker bindings; real DB read/delete/chat/retrieval isolation tests | No automatic migration of legacy public data; process-local limiter and static tokens are a demo deployment boundary, not a complete enterprise identity platform |
| [#8](https://github.com/yanzzzzzzzzz/MediVector-Chat/issues/8) | Dataset contract, review-provenance validation, raw/filtered expansion on/off K=3/5/10 exporter, JSON/Markdown metrics and failure review queue; metric tests | **Pending:** actual 30+ human-reviewed cases, frozen corpus/index, Evaluation Lab repository/integration, measured baseline and human analysis of five failures. Template is intentionally rejected as unreviewed |

Validation: 41 backend tests passed on Python 3.12, including three real PostgreSQL integration
tests, chat regression cases and OpenAI mock/deadline tests. Five frontend HTTP client tests passed,
as did frontend production build, TypeScript checks and full ESLint. Test databases and tokenizer
cache are isolated; no production data or real OpenAI API calls are used.

GitHub Actions now runs the backend suite with PostgreSQL on Python 3.11 and 3.12, plus frontend
HTTP client tests, ESLint and production build on Node 24. CI status is reported by each workflow
run rather than inferred from local checks. See [test instructions](../tests/README.md).

See [experiment instructions](README.md) and [measured synthetic benchmark](reports/hnsw-synthetic.md).


## Institutional source-governance increment (#13–#15)

- #13: additive normalized organization/branch/department/document/version/chunk schema, stable
  version identities, source/license/checksum/validity/ACL metadata, ERD and migration tests.
  Legacy data becomes unapproved/unscoped Draft; an authorized corpus manifest supports evaluation.
- #14: Draft → In Review → Approved / returned Draft → Superseded / Archived, role/scope checks,
  reason/actor/timestamps, atomic superseding with history retention and append-only event guards.
  Future-dated publication scheduling is not implemented; approval waits until effective_from.
- #15: server-owned identity/grants and required institutional scope; approved/effective ACL filtering
  occurs before exact vector ranking, raw mode cannot bypass it, and no evidence means no answer-model
  fallback. Shared organization schemas retain private conversation ownership.
- #16 partial: citation version IDs, offsets and access revalidation/redaction are implemented,
  with a source-inspection UI. Full PDF attachment flow and ten-query source-viewer coverage remain.
- #17 partial foundation: the source-version workspace exists; generated education drafts and their
  own review/publication/feedback flow remain pending. #18/#19 full rules/snapshots/release gate and
  #20 real interviews/Pilot remain pending. #8 still requires independent human labels.

Validation for this increment: 53 backend tests, including real PostgreSQL migration/state/ACL/ownership,
source provenance/event integrity and scoped export protocol cases. Frontend HTTP tests, full lint,
TypeScript and production build are checked by CI. See [governance design](../docs/knowledge-governance.md).

## Citation completion (#16)

Added immutable version-bound PDF ingestion/original bytes, page extraction diagnostics, authenticated
attachment reads and source links with cited page/offset/scope. Ten deterministic multi-page QA traces
and permission/withdrawal/invalid-PDF regression cases exercise provenance. OCR is explicitly unsupported;
all-image PDFs are rejected. See `docs/knowledge-governance.md` for endpoint and storage details.

## Generated education workspace (#17)

The separate `/education` workbench generates pending copy from selected approved sources, retains
immutable evidence snapshots and human revision diffs, and requires explicit Reviewer/Admin publication.
Nurse editing/submission, return, publish and withdrawal are covered end-to-end. Reader access is restricted
to published copy whose sources remain valid/authorized. Source/query feedback is linked to exact version
and owned conversation IDs. See `docs/education-workspace.md`; semantic and clinical review remain human
responsibilities, not an automatic consequence of syntactically valid citations.

## Medical evaluation rules (#18)

Added a network-free deterministic source/version/scope/ACL/citation evaluator, JSON/Markdown reports,
19 synthetic controls (five per required negative category), explicit Pass/Fail/Review Required and
same-corpus integration with the retrieval baseline CLI. Unknown semantics do not become Pass.
Rule fixtures remain separate from #8's still-pending independently human-reviewed baseline.

## Experiment audit and release gate (#19)

Added allowlisted model/prompt/corpus/index/dataset/Git/source-code snapshots, private immutable query
trace IDs without copied raw questions/answers, and authenticated publication-review records. Online
publication blocks deterministic Fail and requires explicit Reviewer/Admin review for uncertain semantics.
Offline/CI gates replay frozen traces, bind manual approvals to the exact report hash, cannot override
Fail, emit non-overwriting JSON/Markdown and retain CI reports in run summaries. See `docs/quality-audit.md`.
Human-reviewed clinical baseline and real professional Pilot remain #8/#20 requirements.

## #8 human-review preparation (still open)

Prepared 30 stable-ID candidate cases with a frozen synthetic preview source/manifest packet and human
review worksheet. Python and the independent .NET Lab reject pending-human data; review provenance remains
blank. The separate .NET 10 checkout passes its Release build and synthetic metric/contract self-tests,
but remote repository creation/push is pending. No human-reviewed baseline, clinical claim or five-failure
analysis is fabricated. These external/human completion requirements keep #8 open.

## #20 interview/Pilot preparation (still open)

Prepared a 3–5-participant interview guide, synthetic task protocol, timing/source/citation/revision/error
measurement definitions and an empty anonymized report template in `docs/pilot/`. No participants, consent,
interviews, measurements, adoption findings or validated product hypotheses are invented. Real professional
participation and completed reports are required before #20 can be closed.

## #5 answer-support review handoff (still open)

Added two real Luna responses against synthetic sources for pending human claim/support review, with no
fabricated reviewer or verdict. Deterministic citation validation now accepts both numeric and 索引 markers;
nonexistent citations fail even if semantic review is pending, while pending support annotations cannot Pass.
See `candidates/ANSWER_REVIEW.md`. Actual reviewed semantic-support examples remain necessary before closure.

## #10 scope comparison increment

Added a controlled authorized-scope union diagnostic to compare the same question with and without the
target branch restriction, while never disabling organization/status/validity/ACL enforcement. Real DB
tests cover shared-document dedup and scope denial before embedding; corpus/query drift aborts comparison.
The source assistant engineering workflow is available; actual answer-support review (#5) and independently
reviewed quality baseline (#8) remain explicitly pending rather than being inferred from these mechanics.


## #8 independent Lab remote established — 2026-11-06

Created private `yanzzzzzzzzz/rag-evaluation-lab` through the user's browser and pushed the independently
committed .NET source/self-tests/workflow (`26926f6`, `115c4ed`).
[Independent Lab CI passed](https://github.com/yanzzzzzzzzz/rag-evaluation-lab/actions/runs/42144963691). Human review of the candidate dataset,
real baseline runs and actual failure analyses are still pending. No professional participants are
currently available; the review and Pilot materials remain prepared, not falsely marked as validated.

### 2026-11-06 合成資料實測

已完成 120 次檢索比較及 5 題回答觀察，新增診斷程式與保護測試（後端 93 tests 通過、CI 通過）。詳見 [工程分析](reports/synthetic-analysis-2026-11-06.md)。全部候選標註仍為 pending_human，不能匯入正式 baseline 或 release gate；#5、#8 仍保留人工驗收待辦。


### 2026-11-06 原型表示法控制實驗

固定兩份合成來源、30 題候選題及改寫關閉，完成正文／標題／頁碼／逐頁分塊四組實際 embedding 比較。
加入標題後提議可回答題命中由 16/20 到 20/20，提議無答案題仍返回候選由 3/10 到 2/10；
結果僅適用此小樣本，未改正式索引與門檻。下一步擴充語料與獨立題目，驗證泛化及剩餘誤命中。
新增 7 項保護測試；後端 100 項中 70 項通過、30 項資料庫整合測試略過。
詳見 [比較分析](reports/representation-analysis-2026-11-06.md)。#5/#8/#20 保持未完成。


### 2026-11-06 擴充挑戰集與門檻重播

新增 12 份虛構行政／文件管理來源、44 題待審候選題，完成四組表示法及 32 組離線門檻比較。
標題＋正文讓提議可回答題命中由 30/36 到 36/36，但提議無答案題返回候選由 5/8 增至 6/8。
降低門檻也會犧牲正確來源，因此未更改線上索引／設定。下一步優先比較來源支持性與可回答性判斷。
詳見 [擴充分析](reports/prototype-challenge-analysis-2026-11-06.md)。104 項測試中 74 通過、30 項 DB 整合測試略過；無人工驗證或臨床品質宣稱。


### 2026-11-06 來源可回答性與可選問答閘門

先提交前輪檢查點 `0dc78cd`。新增逐項資訊需求估計、原文引文校驗、固定候選隔離比較，
以及 `SOURCE_SUPPORT_CHECK_ENABLED`（預設關閉）的院所生成前檢查。未通過時跳過答案模型；
通過時只交付有支持引文的片段，歷史與稽核只保存估計摘要，未啟用本機預覽開關。
44 題待審合成比較：36 題提議可回答均保留接受，8 題提議無答案均不接受（含一題不確定），
不可視為人工或臨床驗證。完整 119 項後端測試在一次性 pgvector 容器通過。
詳見 [實作與實測](reports/source-support-analysis-2026-11-06.md)。#5/#8/#20 保持未完成。


### 2026-11-06 來源判斷邊界與回歸修正

新增 18 題直接片段邊界案例與 4 題涵蓋範圍／實質規定成對案例。首次發現一題把「未列資訊」
當成足夠來源；修正後的原 44 題回歸曾新增一題誤拒。再加入標題情境（引文仍限正文）後，
最終 44＋18＋4 題與候選標註一致；原始失敗與中途退步均保留，未將程式候選標註當人工真值。
完整 123 項後端測試在一次性 pgvector 容器通過。預覽開關仍關閉，下一步為本機端到端操作驗證。
詳見 [邊界修正分析](reports/source-support-boundary-analysis-2026-11-06.md)。#5/#8/#20 保持未完成。


### 2026-11-06 本機預覽啟用與實際驗證

本機預覽已以 `cb5b37d` 重建，透過額外 Compose 覆寫啟用來源檢查；專案預設仍為 false，
未修改 `.env` 或來源資料。四個實際 API 情境確認回答／拒答、引用版本、歷史摘要與稽核模型呼叫旗標，
來源 manifest 前後未變。Chrome 另核對回答、拒答、引用原文、追溯視窗、歷史還原，以及原始 PDF 第三頁內容。
新增可重用的 `docker-compose.source-support.yml` 與 [預覽驗證／回復說明](../docs/preview-validation.md)。
這不取代 #5/#8/#20 的人工驗證。已記錄 legacy 入口與非 UUID 輸入處理等後續整理項目。


### 2026-11-06 入口、UUID 與文字呈現修正

`807192f` 修正院所歷史頁誤用 legacy API、對話 ID 無效值回 500，以及回答粗體／引用呈現；
`3e12d5b` 讓「新查詢」直接開啟查詢表單。新增授權工作區模式端點，院所歷史頁不提供無範圍聊天輸入。
完整後端 126 項（含 DB 整合）、前端 10 項測試、lint／型別／build 通過，並已重建本機預覽。
詳見 [入口驗證](../docs/entry-polish-validation.md)。未變更來源或關閉人工待辦。


### 2026-11-06 暫時免設定連線

依使用者測試需求，`daf3868` 新增明確指定示範帳號的本機自動連線覆寫，隱藏手動連線控制；
未將 Token 寫入前端，預設驗證仍保留，機構／範圍／角色檢查仍適用。已啟用於只綁定 localhost 的預覽，
全新分頁與不帶 Token 的文件／合成問答實測通過。後端 130、前端 13 項測試及 lint／型別／build 通過。
恢復方式與實測見 [預覽說明](../docs/preview-validation.md)。
