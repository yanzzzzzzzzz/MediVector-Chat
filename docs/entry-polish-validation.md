# 原型入口與輸入修正 — 2026-11-06

## 修正結果

- 院所帳號的 `/` 改為查詢紀錄閱讀頁，透過已授權的 `/api/session` 判斷工作區模式，不再載入 legacy 文件 API，也不提供缺少院區／科別的聊天輸入。
- 「新查詢」與頁面內的查詢連結導向 `/knowledge?view=query`，直接開啟院所查詢表單；「文件工作台」仍進入文件清單。個人 legacy 帳號保留原有文件／聊天流程。
- `POST /api/ask`、讀取及刪除對話的 ID 皆在 API 入口驗證 UUID，不合法值回 400。省略問答對話 ID 時產生新的 UUID，傳入既有 UUID 才延續同一對話。
- 瀏覽器標題、院所側欄與頁尾改用「醫療文件知識管理原型」。舊「開啟 Demo 對話」入口改稱「查閱對話紀錄」。
- 回答與歷史訊息共用安全文字元件，呈現粗體及數字／索引引用。未知引用與其他標記保持文字，沒有使用 `v-html` 或執行原始 HTML。

## 自動驗證

完整後端 126 項測試在一次性 PostgreSQL／pgvector 容器通過；前端 10 項測試、完整 ESLint、TypeScript 與 production build 通過。

新增測試確認不合法 ID 不會進入問答、歷史查詢或刪除函式；省略 ID 會產生不同的有效 UUID；工作區模式沿用身分授權且不回傳憑證。前端測試涵蓋有效與未知引用、粗體內引用，以及將 HTML／腳本式連結保留為純文字。

本機 pnpm 11 的預設執行前檢查曾嘗試重建依賴，因沙箱與無 TTY 中止；後續使用既有依賴並以 `--config.verify-deps-before-run=false` 執行驗證，未修改 package 或 lockfile。Docker 仍使用既有 pnpm 10 build 流程。

## 本機預覽驗證

本輪已將兩個程式提交 `807192f`、`3e12d5b` 重建到既有 `medivector-preview`。來源檢查保持啟用，沒有更動 `.env`、來源文件或資料庫 volume。

實際 HTTP 已確認工作區模式為 institutional，無效 ID 的 POST／GET／DELETE 都回 400，頁面標題與語系正確。
Chrome 另確認院所歷史頁顯示「院所查詢紀錄」、可還原已保存回答、粗體不再出現星號、引用按鈕可開啟原文，以及「新查詢」在最終版本直接開啟 `/knowledge?view=query` 表單（含院區與科別）。

完整記錄：[本機入口驗證](../evaluation/reports/preview-entry-validation-2026-11-06.json)。此為工程驗證，不是人工醫療審查或真人 Pilot。

## 使用位置

- 文件與審核：http://127.0.0.1:8000/knowledge
- 直接查詢：http://127.0.0.1:8000/knowledge?view=query
- 已儲存對話：http://127.0.0.1:8000/

啟用與關閉來源檢查的指令仍見 [預覽操作說明](preview-validation.md)。
