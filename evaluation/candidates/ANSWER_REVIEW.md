# 回答引用支持性人工審查（#5，待完成）

`answer-support-v1.json` 保存兩份以合成核准來源進行的真實模型回答，包括一個洗手問題與一個缺乏檢查禁食規範的問題。
這不是已完成的臨床評估：`review_status` 保持 `pending_human`，審查者／時間空白，`claims` 尚未切分。

請實際審查者逐項完成：

1. 把回答切成可獨立核對的陳述，標記 `requires_evidence`；拒答或限制說明不應誤當成院內規範。
2. 對每個陳述列出實際引用編號；確認引用確實存在於該次 references，而非其他版本或目前另查的文件。
3. 將該段陳述與引用原文比較，在 `support` 記錄 true（支持）、false（不支持）或 null（不確定／需進一步審查）。
4. 記錄理由、實際 reviewer ID 及帶時區時間；未確定的語意保留待審，不用距離分數或相似詞取代判斷。
5. 完成後才修改 review_status；若發現文件或回答問題，使用工作台回報，保留 query_trace_id 與版本。

陳述格式範例（只是欄位示意，不能複製當標註）：

```json
{"text":"待核對的完整陳述","requires_evidence":true,"citations":[1],"support":{"1":null}}
```

執行 `python -m evaluation.faithfulness evaluation/candidates/answer-support-v1.json <新報告路徑>`。
待審資料不能得到 Pass；不存在的引用仍直接 Fail。現有 `faithfulness_cases.json` 是合成邏輯測試，
不是專業人員已審查的醫療案例。實際語意標註完成前 #5 保持開啟。
