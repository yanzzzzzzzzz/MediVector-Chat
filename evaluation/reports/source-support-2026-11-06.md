# 來源可回答性隔離比較（AI 估計，未經人工審查）

Only model-estimated source sufficiency, not an answer or a semantic/clinical guarantee. Verbatim quotes establish provenance, not entailment or complete requirement decomposition. Scores use unreviewed program-authored proposed labels on the same synthetic challenge. Retrieval-only candidate presence is an ablation comparator, not existing chat acceptance behavior. No live endpoint/index change. Prompt token usage is not a monetary cost calculation. Non-sufficient and model failures are treated as non-acceptance, with failures counted separately.

| 策略 | 提議可回答題接受 | 提議可回答題拒絕 | 提議無答案題接受 | 提議無答案題拒絕 |
|---|---:|---:|---:|---:|
| 有候選就接受（比較基準） | 36 | 0 | 6 | 2 |
| 來源可回答性估計 | 36 | 0 | 0 | 8 |

模型檢查 P50/P95：1900.8899999999999 / 2983.43 ms。
Token usage：{'prompt_tokens': 39459, 'completion_tokens': 4242, 'total_tokens': 43701}。

API 失敗：0；不合格式／引用無法核對：0。

| 題號 | 問題 | 模型估計 | 與候選標註一致 |
|---|---|---|---|
| challenge-001 | 第一次來看門診，到了以後要先去哪裡？ | sufficient | True |
| challenge-002 | 初次就診當天要帶哪一張紙？ | sufficient | True |
| challenge-003 | 第一次看診忘了帶通知文件怎麼處理？ | sufficient | True |
| challenge-004 | 已經有回診預約，要去哪裡完成報到？ | sufficient | True |
| challenge-005 | 回來複診還要再拿初診號碼嗎？ | sufficient | True |
| challenge-006 | 複診用的卡片找不到，在哪裡補發？ | sufficient | True |
| challenge-007 | 辦住院手續要到哪個櫃台？ | sufficient | True |
| challenge-008 | 辦入院要準備哪兩份文件？ | sufficient | True |
| challenge-009 | 入院表格忘記寫聯絡資料，找誰處理？ | sufficient | True |
| challenge-010 | 要離院了，行政資料先到哪裡核對？ | sufficient | True |
| challenge-011 | 離院的收據要再拿一份，去哪裡辦？ | sufficient | True |
| challenge-012 | 離院資料名字打錯，可以自己改嗎？ | sufficient | True |
| challenge-013 | 內容寫好以後，應送到哪裡給人檢查？ | sufficient | True |
| challenge-014 | 審查退件時必須留下什麼說明？ | sufficient | True |
| challenge-015 | 通過審查後，系統會保存哪些追蹤資訊？ | sufficient | True |
| challenge-016 | 已經發出去的資料版本弄錯，審核者要怎麼處理？ | sufficient | True |
| challenge-017 | 下架後一般使用者還查得到那份內容嗎？ | sufficient | True |
| challenge-018 | 已通過的原稿可以直接蓋掉，換成修正版嗎？ | sufficient | True |
| challenge-019 | 想拿公開行政資料的紙本副本，要填哪個表？ | sufficient | True |
| challenge-020 | 影印申請交到哪個單位？ | sufficient | True |
| challenge-021 | 送出紙本副本申請後，何時可以拿到？ | sufficient | True |
| challenge-022 | 只想證明當天有到場，應該填哪張表？ | sufficient | True |
| challenge-023 | 拿到場證明時，要出示哪個憑據？ | sufficient | True |
| challenge-024 | 到場證明寫錯日期，去哪裡改？ | sufficient | True |
| challenge-025 | 約好的時間沒變，但服務位置換了，要去哪裡核對？ | sufficient | True |
| challenge-026 | 收到換地點的信，預約時間也會一起改嗎？ | sufficient | True |
| challenge-027 | 手上有兩張不同位置的通知，該看哪張？ | sufficient | True |
| challenge-028 | 剛接手維護工作，第一次登入該用哪種帳號？ | sufficient | True |
| challenge-029 | 練習全部做完，要把哪個表送給哪個小組？ | sufficient | True |
| challenge-030 | 新人演練用的帳號什麼時候停掉？ | sufficient | True |
| challenge-031 | 出發之前，服務地點要用什麼資料確認？ | sufficient | True |
| challenge-032 | 到了服務中心，確認信要拿給哪個櫃台？ | sufficient | True |
| challenge-033 | 行政事情辦完後，訪客證要交到哪裡？ | sufficient | True |
| challenge-034 | 要來取文件，案件號碼應從哪封信找？ | sufficient | True |
| challenge-035 | 取件收條要交給哪個顏色的文件櫃台？ | sufficient | True |
| challenge-036 | 領到的紙本缺頁，離開前該找誰？ | sufficient | True |
| challenge-037 | 大腸鏡之前要停藥幾天？ | insufficient | True |
| challenge-038 | MRI 檢查前必須空腹幾個小時？ | insufficient | True |
| challenge-039 | 診斷證明要付多少費用？ | insufficient | True |
| challenge-040 | 到場證明可以當成診斷證明使用嗎？ | uncertain | True |
| challenge-041 | 紙本副本能不能寄到國外？ | insufficient | True |
| challenge-042 | 回診卡可以讓其他家人借用嗎？ | insufficient | True |
| challenge-043 | 門診報到可以遲到多久？ | insufficient | True |
| challenge-044 | 住院保證金需要多少錢？ | insufficient | True |
