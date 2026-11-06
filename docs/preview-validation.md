# 本機原型預覽驗證 — 2026-11-06

## 首輪啟用狀態

本機 `medivector-preview` 的 app 已重建為程式版本 `cb5b37dfb10a267ab4c9a8dbdd74c2dd5c5b9af4`，
`SOURCE_SUPPORT_CHECK_ENABLED=true`。頁面為 http://127.0.0.1:8000/knowledge。
使用既有本機示範帳號與合成文件，沒有修改 `.env`、文件原文、核准狀態或索引。
只新增本輪示範查詢對話；來源 manifest 在四個 API 情境執行前後一致。

## 已完成的實際驗證

| 情境 | 實際結果 | 答案模型 |
|---|---|---|
| 示範洗手文件至少搓洗多久 | 回答 20 秒並附來源 | 有呼叫 |
| 大腸鏡前何時停用藥物 | 雖找到洗手文件，仍回覆資訊不足 | 未呼叫 |
| 量子通訊封包格式 | 沒有來源，回覆無法確認 | 未呼叫 |
| 英文 PDF 示範中的預約通知 | 找到 PDF 並回答需攜帶通知 | 有呼叫 |

四個情境均確認：來源判斷摘要已保存至對話歷史、引用可讀取且版本 ID 一致、稽核記錄有正確的
`answer_model_invoked` 與已啟用開關。這是實際本機 HTTP／模型／資料庫流程，不是 mock。
每項完整驗證約 3.4–7.8 秒，包含問答、讀取歷史與稽核等請求，不是單純生成延遲。

Chrome 畫面另實際操作有來源問題、資訊不足拒答、原文引用按鈕、查詢追溯視窗與歷史對話還原。
來源核對視窗顯示洗手文件 v1.1、字元位置與原文。歷史對話還原後能看到原本的資訊不足回覆。
PDF 引用核對視窗顯示 v1、第 1、3 頁與字元 0–177；點擊載入原件後，Chrome PDF 閱讀器
顯示共三頁，切到第 3 頁可核對「bring the appointment notice」。

完整 API 結果：[合成預覽 smoke report](../evaluation/reports/preview-smoke-2026-11-06.json)。
本輪只是少量合成操作驗證，不是正式 baseline、醫療專業審查或真人 Pilot。

## 重啟並啟用

以下指令用於已存在的本機 `medivector-preview`；`/tmp/medivector-preview-compose.yml` 是目前
預覽使用的 PostgreSQL port 覆寫檔。從專案根目錄執行，保留原資料庫：

```sh
APP_GIT_SHA="$(git rev-parse HEAD)" docker compose -p medivector-preview \
  -f docker-compose.yml \
  -f /tmp/medivector-preview-compose.yml \
  -f docker-compose.source-support.yml \
  up -d --build --no-deps app
```

本輪實際啟動時使用 `/tmp/medivector-support-preview.yml`，內容與新增的
`docker-compose.source-support.yml` 相同，只明確設定 app 的來源檢查開關。

## 關閉來源檢查

移除來源檢查覆寫檔，並明確將基礎設定設為 false；不刪除資料或 volume：

```sh
SOURCE_SUPPORT_CHECK_ENABLED=false docker compose -p medivector-preview \
  -f docker-compose.yml \
  -f /tmp/medivector-preview-compose.yml \
  up -d --no-deps app
```

已用 Compose config 確認上述回復設定為 `false`，沒有實際關閉目前預覽。專案預設仍是 false；
目前這個本機預覽因額外覆寫而啟用。

## 操作注意

首輪操作曾發現院所帳號進入舊 `/` Demo 時載入不適用的 legacy API，以及粗體標記原樣顯示。
後續已修正入口與格式呈現，`/` 對院所帳號作為歷史閱讀頁，新問題改到 `/knowledge?view=query`。
詳見 [最新入口修正與驗證](entry-polish-validation.md)。

初次驗證腳本誤用帶前綴的非 UUID 對話 ID，伺服器回 500；改用 UI 同樣採用的 UUID 後四項通過。
後續已補上 UUID 輸入驗證，不合法值回 400；首輪記錄保留於此，最新行為見入口修正文件。


## 暫時免設定連線（使用者測試模式）

依使用者要求，本機預覽已額外套用 `docker-compose.demo.yml`，自動使用既有 `local-admin`
示範工作空間，隱藏連線設定與憑證輸入。開全新分頁即可測試，不需帶 Token；所有測試頁面共用此示範帳號。
正式預設仍要求授權，`.env` 及原有憑證未修改。移除 demo 覆寫檔、清空 `DEMO_AUTO_CONNECT_USER`
再重建 app／重載頁面，就會恢復手動連線。完整指令見 [README](../README.md)。

已實測無 Authorization header 可載入文件與完成一個合成問答；新 Chrome 分頁直接顯示本機示範工作空間與查詢表單。
後端 130 項（含真實 pgvector）、前端 13 項測試及 lint／型別／build 通過。
[免連線設定實測記錄](../evaluation/reports/demo-auto-connection-2026-11-06.json)。
