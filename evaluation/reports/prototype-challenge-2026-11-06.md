# 文件表示法比較（合成資料，未經人工審查）

Synthetic ablation with program-authored sources/questions and unreviewed proposed labels; not an independent holdout or real-world generalization study. No live ACL, database ranking, generation, clinical validation or latency benchmark. Page splitting changes chunk count. Query expansion is off for every variant. A source/version match does not establish that a retrieved page supports an answer.

| 表示法 | chunks | 暫定 Recall@5 | 暫定 MRR@5 | 暫定片段精確率 | 暫定證據覆蓋 | 提議無答案題仍返回候選 |
|---|---:|---:|---:|---:|---:|---:|
| body | 13 | 0.8333333333333334 | 0.750925925925926 | 0.4643518518518518 | 0.8333333333333334 | 0.625 |
| title | 13 | 1.0 | 0.8449074074074074 | 0.48379629629629634 | 1.0 | 0.75 |
| title_pages | 13 | 1.0 | 0.8449074074074074 | 0.48379629629629634 | 1.0 | 0.75 |
| page_chunks | 17 | 1.0 | 0.8865740740740741 | 0.4986111111111111 | 1.0 | 0.75 |

## 逐題比較

| 題號 | body | title | title_pages | page_chunks |
|---|---|---|---|---|
| challenge-001 | 命中 | 命中 | 命中 | 命中 |
| challenge-002 | 命中 | 命中 | 命中 | 命中 |
| challenge-003 | 命中 | 命中 | 命中 | 命中 |
| challenge-004 | 命中 | 命中 | 命中 | 命中 |
| challenge-005 | 命中 | 命中 | 命中 | 命中 |
| challenge-006 | 命中 | 命中 | 命中 | 命中 |
| challenge-007 | 命中 | 命中 | 命中 | 命中 |
| challenge-008 | 命中 | 命中 | 命中 | 命中 |
| challenge-009 | 命中 | 命中 | 命中 | 命中 |
| challenge-010 | 命中 | 命中 | 命中 | 命中 |
| challenge-011 | 命中 | 命中 | 命中 | 命中 |
| challenge-012 | 命中 | 命中 | 命中 | 命中 |
| challenge-013 | 命中 | 命中 | 命中 | 命中 |
| challenge-014 | 命中 | 命中 | 命中 | 命中 |
| challenge-015 | 命中 | 命中 | 命中 | 命中 |
| challenge-016 | 命中 | 命中 | 命中 | 命中 |
| challenge-017 | 命中 | 命中 | 命中 | 命中 |
| challenge-018 | 命中 | 命中 | 命中 | 命中 |
| challenge-019 | 命中 | 命中 | 命中 | 命中 |
| challenge-020 | 命中 | 命中 | 命中 | 命中 |
| challenge-021 | 命中 | 命中 | 命中 | 命中 |
| challenge-022 | 命中 | 命中 | 命中 | 命中 |
| challenge-023 | 命中 | 命中 | 命中 | 命中 |
| challenge-024 | 命中 | 命中 | 命中 | 命中 |
| challenge-025 | 命中 | 命中 | 命中 | 命中 |
| challenge-026 | 命中 | 命中 | 命中 | 命中 |
| challenge-027 | 命中 | 命中 | 命中 | 命中 |
| challenge-028 | 命中 | 命中 | 命中 | 命中 |
| challenge-029 | 命中 | 命中 | 命中 | 命中 |
| challenge-030 | 命中 | 命中 | 命中 | 命中 |
| challenge-031 | 漏檢 | 命中 | 命中 | 命中 |
| challenge-032 | 漏檢 | 命中 | 命中 | 命中 |
| challenge-033 | 漏檢 | 命中 | 命中 | 命中 |
| challenge-034 | 漏檢 | 命中 | 命中 | 命中 |
| challenge-035 | 漏檢 | 命中 | 命中 | 命中 |
| challenge-036 | 漏檢 | 命中 | 命中 | 命中 |
| challenge-037 | 無候選 | 無候選 | 無候選 | 無候選 |
| challenge-038 | 無候選 | 仍返回候選 | 仍返回候選 | 仍返回候選 |
| challenge-039 | 仍返回候選 | 仍返回候選 | 仍返回候選 | 仍返回候選 |
| challenge-040 | 仍返回候選 | 仍返回候選 | 仍返回候選 | 仍返回候選 |
| challenge-041 | 無候選 | 無候選 | 無候選 | 無候選 |
| challenge-042 | 仍返回候選 | 仍返回候選 | 仍返回候選 | 仍返回候選 |
| challenge-043 | 仍返回候選 | 仍返回候選 | 仍返回候選 | 仍返回候選 |
| challenge-044 | 仍返回候選 | 仍返回候選 | 仍返回候選 | 仍返回候選 |
