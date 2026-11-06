# 文件表示法比較（合成資料，未經人工審查）

Synthetic two-source ablation with unreviewed proposed labels. No live ACL, database ranking, generation, clinical validation or latency benchmark. Page splitting changes chunk count. Query expansion is off for every variant. A source/version match does not establish that a retrieved page supports an answer.

| 表示法 | chunks | 暫定 Recall@5 | 暫定 MRR@5 | 提議無答案題仍返回候選 |
|---|---:|---:|---:|---:|
| body | 2 | 0.8 | 0.8 | 0.3 |
| title | 2 | 1.0 | 1.0 | 0.2 |
| title_pages | 2 | 1.0 | 1.0 | 0.2 |
| page_chunks | 3 | 1.0 | 1.0 | 0.2 |

## 逐題比較

| 題號 | body | title | title_pages | page_chunks |
|---|---|---|---|---|
| candidate-001 | 命中 | 命中 | 命中 | 命中 |
| candidate-002 | 命中 | 命中 | 命中 | 命中 |
| candidate-003 | 命中 | 命中 | 命中 | 命中 |
| candidate-004 | 命中 | 命中 | 命中 | 命中 |
| candidate-005 | 命中 | 命中 | 命中 | 命中 |
| candidate-006 | 命中 | 命中 | 命中 | 命中 |
| candidate-007 | 命中 | 命中 | 命中 | 命中 |
| candidate-008 | 命中 | 命中 | 命中 | 命中 |
| candidate-009 | 命中 | 命中 | 命中 | 命中 |
| candidate-010 | 命中 | 命中 | 命中 | 命中 |
| candidate-011 | 命中 | 命中 | 命中 | 命中 |
| candidate-012 | 命中 | 命中 | 命中 | 命中 |
| candidate-013 | 命中 | 命中 | 命中 | 命中 |
| candidate-014 | 命中 | 命中 | 命中 | 命中 |
| candidate-015 | 命中 | 命中 | 命中 | 命中 |
| candidate-016 | 漏檢 | 命中 | 命中 | 命中 |
| candidate-017 | 漏檢 | 命中 | 命中 | 命中 |
| candidate-018 | 漏檢 | 命中 | 命中 | 命中 |
| candidate-019 | 漏檢 | 命中 | 命中 | 命中 |
| candidate-020 | 命中 | 命中 | 命中 | 命中 |
| candidate-021 | 無候選 | 無候選 | 無候選 | 無候選 |
| candidate-022 | 無候選 | 無候選 | 無候選 | 無候選 |
| candidate-023 | 無候選 | 無候選 | 無候選 | 無候選 |
| candidate-024 | 仍返回候選 | 仍返回候選 | 仍返回候選 | 仍返回候選 |
| candidate-025 | 無候選 | 無候選 | 無候選 | 無候選 |
| candidate-026 | 無候選 | 無候選 | 無候選 | 無候選 |
| candidate-027 | 無候選 | 無候選 | 無候選 | 無候選 |
| candidate-028 | 仍返回候選 | 仍返回候選 | 仍返回候選 | 仍返回候選 |
| candidate-029 | 無候選 | 無候選 | 無候選 | 無候選 |
| candidate-030 | 仍返回候選 | 無候選 | 無候選 | 無候選 |
