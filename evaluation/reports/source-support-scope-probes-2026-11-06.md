# 來源可回答性隔離比較（AI 估計，未經人工審查）

Only model-estimated source sufficiency, not an answer or a semantic/clinical guarantee. Verbatim quotes establish provenance, not entailment or complete requirement decomposition. Scores use unreviewed program-authored proposed labels on the same synthetic challenge. Retrieval-only candidate presence is an ablation comparator, not existing chat acceptance behavior. No live endpoint/index change. Prompt token usage is not a monetary cost calculation. Non-sufficient and model failures are treated as non-acceptance, with failures counted separately.

| 策略 | 提議可回答題接受 | 提議可回答題拒絕 | 提議無答案題接受 | 提議無答案題拒絕 |
|---|---:|---:|---:|---:|
| 有提供片段就接受（無檢索比較） | 2 | 0 | 2 | 0 |
| 來源可回答性估計 | 2 | 0 | 0 | 2 |

模型檢查 P50/P95：1467.95 / 1662.66 ms。
Token usage：{'prompt_tokens': 2701, 'completion_tokens': 232, 'total_tokens': 2933}。

API 失敗：0；不合格式／引用無法核對：0。

| 題號 | 問題 | 模型估計 | 與候選標註一致 |
|---|---|---|---|
| scope-probe-001 | 這份文件有寫乙院區的領件時間嗎？ | sufficient | True |
| scope-probe-002 | 我在乙院區，交件之後要等幾天才能取件？ | insufficient | True |
| scope-probe-003 | 這項影本服務有提供電子郵件副本嗎？ | sufficient | True |
| scope-probe-004 | 申請者可以改收電子郵件版本嗎？ | insufficient | True |
