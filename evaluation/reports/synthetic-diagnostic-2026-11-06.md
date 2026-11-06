# 合成資料工程診斷（未經人工審查，不是正式 baseline）

Candidate labels have NOT been human reviewed. All relevance scores are provisional comparisons against proposed labels, not verified Recall or clinical quality. No answer generation or semantic faithfulness is measured. Raw nearest-neighbor returns do not establish answerability. K=3/5/10 reuse one max-K result; a tiny corpus cannot distinguish those K settings. Sequential latency includes embedding/provider variability; raw expansion runs include rewrite cost while filtered runs replay the rewrite, so their latency is not a causal raw-vs-filter speed comparison. This report is not eligible for a release gate or the independent Lab verified-baseline command.

文件版本：2；chunks：2。
以下分數只與候選標註比較，不代表人工確認的檢索品質。

| Mode | 改寫 | K | 暫定 Recall | 暫定 MRR | 暫定 Hit | 暫定證據覆蓋 | 提議無答案題仍返回候選 | P50 ms | P95 ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| raw | False | 3 | 1.0 | 0.9 | 1 | 1.0 | 1 | 306.7 | 638.3 |
| raw | False | 5 | 1.0 | 0.9 | 1 | 1.0 | 1 | 306.7 | 638.3 |
| raw | False | 10 | 1.0 | 0.9 | 1 | 1.0 | 1 | 306.7 | 638.3 |
| filtered | False | 3 | 0.8 | 0.8 | 0.8 | 0.8 | 0.3 | 314.4 | 528.9 |
| filtered | False | 5 | 0.8 | 0.8 | 0.8 | 0.8 | 0.3 | 314.4 | 528.9 |
| filtered | False | 10 | 0.8 | 0.8 | 0.8 | 0.8 | 0.3 | 314.4 | 528.9 |
| raw | True | 3 | 1.0 | 0.925 | 1 | 1.0 | 1 | 1884.8 | 3946.1 |
| raw | True | 5 | 1.0 | 0.925 | 1 | 1.0 | 1 | 1884.8 | 3946.1 |
| raw | True | 10 | 1.0 | 0.925 | 1 | 1.0 | 1 | 1884.8 | 3946.1 |
| filtered | True | 3 | 0.8 | 0.8 | 0.8 | 0.8 | 0.4 | 371.4 | 508.0 |
| filtered | True | 5 | 0.8 | 0.8 | 0.8 | 0.8 | 0.4 | 371.4 | 508.0 |
| filtered | True | 10 | 0.8 | 0.8 | 0.8 | 0.8 | 0.4 | 371.4 | 508.0 |

## 待人工核對的觀察

下列是與候選標註的差異，不是已確認的醫療錯誤或失敗根因。

### candidate-016：PDF 合成範例要攜帶什麼文件？
- 改寫 False：proposed relevant document missing after filtering; proposed evidence span not covered
- 改寫 True：proposed relevant document missing after filtering; proposed evidence span not covered

### candidate-017：PDF 範例屬於正式臨床文件還是流程示範？
- 改寫 False：proposed relevant document missing after filtering; proposed evidence span not covered
  - 版本 `abcd691e-7fa5-4057-a696-9797efc87465`，distance=0.6163413618394997
- 改寫 True：proposed relevant document missing after filtering; proposed evidence span not covered

### candidate-018：PDF 第一頁的準備事項是什麼？
- 改寫 False：proposed relevant document missing after filtering; proposed evidence span not covered
  - 版本 `abcd691e-7fa5-4057-a696-9797efc87465`，distance=0.6356805363683528
- 改寫 True：proposed relevant document missing after filtering; proposed evidence span not covered

### candidate-019：PDF 第三頁的準備事項是什麼？
- 改寫 False：proposed relevant document missing after filtering; proposed evidence span not covered
  - 版本 `abcd691e-7fa5-4057-a696-9797efc87465`，distance=0.6137002359622101
- 改寫 True：proposed relevant document missing after filtering; proposed evidence span not covered

### candidate-024：本院大腸鏡檢查前何時停用藥物？
- 改寫 False：filtered candidates returned for a proposed no-answer question; relevance needs review
  - 版本 `abcd691e-7fa5-4057-a696-9797efc87465`，distance=0.5753884223030286
- 改寫 True：filtered candidates returned for a proposed no-answer question; relevance needs review
  - 版本 `abcd691e-7fa5-4057-a696-9797efc87465`，distance=0.5740224163815746
