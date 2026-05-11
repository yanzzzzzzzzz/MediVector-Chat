# Vector DB 中文問答 Demo

這是一個本機執行的中文 RAG 測試專案。它使用 Weaviate 作為 vector DB，OpenAI embeddings 產生向量，並用 GPT 根據搜尋到的參考資料回答問題。

## 功能

- 查看目前 Weaviate collection 裡的中文衛教資料
- 新增資料時自動呼叫 OpenAI embedding，並寫入 vector DB
- 刪除單筆 vector DB 資料
- 問答時先搜尋 vector DB，再把參考資料交給 GPT
- 回答中會標記實際使用的參考來源，例如 `[1]`
- 回答中的 `[1]`、`[2]` 可點擊查看原始參考資料
- 沒有足夠相關參考時，不會在回答中加索引
- 同一頁對話保留最近 10 則訊息作短期記憶
- Enter 送出問題，Shift+Enter 換行
- 新增、刪除、載入資料、AI 思考中都有 loading 狀態
- 每筆資料可查看 embedding 維度、前段預覽與完整數字 array
- 每次問答的參考來源會顯示 distance

## 檔案

- `app.py`：Web app 後端、前端頁面、OpenAI 呼叫、Weaviate 操作
- `test.py`：CLI 測試版 RAG 流程
- `docker-compose.yml`：啟動 Weaviate
- `requirements.txt`：Python 套件需求

## 需求

- Docker Desktop
- Python 3.11
- OpenAI API Key
- Python packages:

```powershell
pip install -r requirements.txt
```

如果目前 `.venv` 壞掉或 Python 指向異常，可以重建虛擬環境。

## 啟動 Weaviate

在專案目錄執行：

```powershell
docker compose up -d
```

確認狀態：

```powershell
docker compose ps
```

Weaviate 預設會跑在：

```text
http://127.0.0.1:8080
```

## 啟動 Web App

先設定 OpenAI API Key：

```powershell
$env:OPENAI_API_KEY="你的 API key"
```

一般 Python 可用時：

```powershell
python app.py
```

如果 Windows Store Python 路徑有問題，本機目前可用的啟動方式是：

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) '.venv\Lib\site-packages')
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.11_3.11.2544.0_x64__qbz5n2kfra8p0\python3.11.exe' app.py
```

開啟頁面：

```text
http://127.0.0.1:8000
```

## 重啟 Web App

先找出 8000 port 的 PID：

```powershell
netstat -ano | Select-String ':8000'
```

停止舊服務：

```powershell
Stop-Process -Id <PID> -Force
```

再重新執行 `app.py`。

如果只是要重新整理畫面，在瀏覽器按 `Ctrl+R` 即可。

## 使用方式

### 新增資料

按左側工具列的「+新增資料」，會開啟新增資料視窗。填入：

- 來源 ID：可留空，系統會自動產生
- 標題
- 來源
- 內容

按「新增並 embedding」後，按鈕會鎖定並顯示 loading。成功後清單會自動刷新，且資料依建立時間由新到舊排序。

### 刪除資料

按單筆資料右上角「刪除」。刪除中會鎖定該按鈕並顯示 loading，完成後清單會重新整理。

### 問答

在右側輸入問題：

- `Enter`：送出
- `Shift+Enter`：換行

送出後會顯示「思考中」。後端會先將當前問題 embedding，搜尋 vector DB，再把相關資料交給 GPT 回答。

如果回答內有 `[1]`、`[2]` 這類引用標記，可以直接點擊查看原始參考資料。

## API

### 取得資料清單

```http
GET /api/documents
```

回傳目前 vector DB 內的資料，依 `created_at` 新到舊排序。

### 新增資料

```http
POST /api/documents
Content-Type: application/json

{
  "source_id": 123,
  "title": "年輕人健身衛教",
  "source": "GPT create",
  "content": "健身前應先熱身，重量循序增加..."
}
```

新增時會呼叫 OpenAI embeddings。

### 刪除資料

```http
DELETE /api/documents/{uuid}
```

### 詢問 GPT

```http
POST /api/ask
Content-Type: application/json

{
  "conversation_id": "browser-session-id",
  "question": "年輕人健身要注意什麼？"
}
```

## 環境變數

| 名稱 | 預設值 | 說明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 無 | 必填，用於 embeddings 與 GPT |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | embedding 模型 |
| `OPENAI_CHAT_MODEL` | `gpt-4.1-mini` | 回答用模型 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI API base URL |
| `TOP_K` | `3` | vector search 最多取幾筆 |
| `MAX_REFERENCE_DISTANCE` | `0.45` | 絕對 distance 上限 |
| `REFERENCE_DISTANCE_MARGIN` | `0.04` | 只保留最佳命中 distance 附近的參考 |
| `MEMORY_MESSAGES` | `10` | 保留最近幾則對話給 GPT |
| `HOST` | `127.0.0.1` | Web app host |
| `PORT` | `8000` | Web app port |

## 檢索邏輯

目前 vector DB 搜尋只使用「當前問題」做 embedding，避免先前對話污染檢索結果。短期記憶只會交給 GPT 回答時參考。

搜尋後會做兩層過濾：

1. distance 不可超過 `MAX_REFERENCE_DISTANCE`
2. distance 不可超過「最佳命中 distance + `REFERENCE_DISTANCE_MARGIN`」

因此如果最佳命中是年輕人健身，距離明顯比較遠的高血壓資料會被排除。

## Embedding 與 Distance 視覺化

左側每筆資料會顯示 embedding 摘要：

- 維度數，例如 `1536 維`
- 前 12 個浮點數作預覽
- 展開後可查看完整 embedding array

右側 GPT 回答下方的參考來源會顯示：

- `distance`：Weaviate 回傳的向量距離，越低代表越相似

## 注意事項

- `app.py` 不會在啟動時重建 collection，所以使用者新增的資料會保留。
- `test.py` 是 CLI 測試腳本，會重建 collection 並重新寫入預設資料。
- 問答引用時會對內容相同的參考資料做去重，避免重複列出相同來源。
