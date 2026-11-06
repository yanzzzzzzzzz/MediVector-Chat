# 距離門檻敏感度（重播合成檢索結果）

Reuses exactly the saved candidate distances; no new embedding or generation. Unreviewed synthetic labels only. Tuning and measuring on the same cases is exploratory, not a validated threshold choice. A returned candidate does not establish an incorrect answer.

| 表示法 | 距離上限 | margin | 提議可回答題命中 | 提議無答案題仍返回候選 |
|---|---:|---:|---:|---:|
| body | 0.35 | 0.06 | 4/36 | 1/8 |
| body | 0.35 | 0.12 | 4/36 | 1/8 |
| body | 0.45 | 0.06 | 17/36 | 3/8 |
| body | 0.45 | 0.12 | 18/36 | 3/8 |
| body | 0.55 | 0.06 | 25/36 | 4/8 |
| body | 0.55 | 0.12 | 26/36 | 4/8 |
| body | 0.65 | 0.06 | 28/36 | 5/8 |
| body | 0.65 | 0.12 | 30/36 | 5/8 |
| title | 0.35 | 0.06 | 1/36 | 0/8 |
| title | 0.35 | 0.12 | 1/36 | 0/8 |
| title | 0.45 | 0.06 | 12/36 | 2/8 |
| title | 0.45 | 0.12 | 12/36 | 2/8 |
| title | 0.55 | 0.06 | 29/36 | 4/8 |
| title | 0.55 | 0.12 | 31/36 | 4/8 |
| title | 0.65 | 0.06 | 32/36 | 6/8 |
| title | 0.65 | 0.12 | 36/36 | 6/8 |
| title_pages | 0.35 | 0.06 | 1/36 | 0/8 |
| title_pages | 0.35 | 0.12 | 1/36 | 0/8 |
| title_pages | 0.45 | 0.06 | 12/36 | 2/8 |
| title_pages | 0.45 | 0.12 | 12/36 | 2/8 |
| title_pages | 0.55 | 0.06 | 30/36 | 4/8 |
| title_pages | 0.55 | 0.12 | 31/36 | 4/8 |
| title_pages | 0.65 | 0.06 | 33/36 | 6/8 |
| title_pages | 0.65 | 0.12 | 36/36 | 6/8 |
| page_chunks | 0.35 | 0.06 | 1/36 | 0/8 |
| page_chunks | 0.35 | 0.12 | 1/36 | 0/8 |
| page_chunks | 0.45 | 0.06 | 13/36 | 2/8 |
| page_chunks | 0.45 | 0.12 | 13/36 | 2/8 |
| page_chunks | 0.55 | 0.06 | 29/36 | 4/8 |
| page_chunks | 0.55 | 0.12 | 31/36 | 4/8 |
| page_chunks | 0.65 | 0.06 | 32/36 | 6/8 |
| page_chunks | 0.65 | 0.12 | 36/36 | 6/8 |
