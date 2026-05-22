# Vector DB 中文問答 Demo

這是一個本機執行的中文 RAG 測試專案。它使用 Weaviate 作為 vector DB，OpenAI embeddings 產生向量，並用 GPT 根據搜尋到的參考資料回答問題。

## 功能

- 查看目前 Weaviate collection 裡的中文衛教資料
- 新增資料時自動呼叫 OpenAI embedding，並寫入 vector DB
- 新增資料可直接輸入文字，或上傳 TXT / PDF 衛教檔案
- 上傳的 TXT / PDF 原始檔會保存到 MinIO
- 刪除單筆 vector DB 資料
- 問答時先搜尋 vector DB，再把參考資料交給 GPT
- AI 問答可切換是否使用 RAG 搜尋，方便比較有無引用資料的差異
- 回答中會標記實際使用的參考來源，例如 `[1]`
- 回答中的 `[1]`、`[2]` 可點擊查看原始參考資料
- 沒有足夠相關參考時，不會在回答中加索引
- 同一頁對話保留最近 10 則訊息作短期記憶
- Enter 送出問題，Shift+Enter 換行
- 新增、刪除、載入資料、AI 思考中都有 loading 狀態
- 每筆資料可查看 embedding 維度、前段預覽與完整數字 array
- 每次問答的參考來源會顯示 distance

## 檔案

- `app.py`：Web app 後端、OpenAI 呼叫、Weaviate 操作，並在 production 服務 Vue build 後的靜態檔
- `frontend/medivector-chat-app`：Vue / Vite 前端專案
- `test.py`：CLI 測試版 RAG 流程
- `docker-compose.yml`：啟動 app、Weaviate 與 MinIO
- `Dockerfile`：build Vue 前端並打包 Python app
- `.dockerignore`：排除本機虛擬環境、前端依賴與 build 輸出
- `.env.example`：環境變數範本；複製成 `.env` 後填入自己的設定
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

## 設定環境變數

專案使用根目錄的 `.env` 管理環境變數。先複製範本：

```powershell
Copy-Item .env.example .env
```

然後編輯 `.env`，至少填入：

```dotenv
OPENAI_API_KEY=你的 API key
```

`.env` 會被 Git 忽略，不會提交到 repository。Docker Compose 會自動讀取 `.env`；本機執行 `app.py` 或 `test.py` 時也會載入同一份 `.env`。

## 啟動 Weaviate 與 MinIO

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

MinIO API 與管理介面預設會跑在：

```text
http://127.0.0.1:9000
http://127.0.0.1:9001
```

MinIO 預設帳密：

```text
minioadmin / minioadmin
```

## 使用 Docker 啟動全部服務

確認 `.env` 已設定後，在專案根目錄執行：

```powershell
docker compose up --build -d
```

這會一起啟動：

- `app`：Python API + Vue build 後的前端，`http://127.0.0.1:8000`
- `weaviate`：Vector DB，`http://127.0.0.1:8080`
- `minio`：原始檔保存，API `http://127.0.0.1:9000`，Console `http://127.0.0.1:9001`

啟動後請開：

```text
http://localhost:8000/
```

`http://localhost:8080/v1` 是 Weaviate REST API，看到 JSON 代表 vector DB 正常，不是前端頁面。

查看狀態：

```powershell
docker compose ps
```

停止服務：

```powershell
docker compose down
```

## 啟動後端 API

一般 Python 可用時：

```powershell
python app.py
```

如果 Windows Store Python 路徑有問題，本機目前可用的啟動方式是：

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) '.venv\Lib\site-packages')
& 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.11_3.11.2544.0_x64__qbz5n2kfra8p0\python3.11.exe' app.py
```

後端 API：

```text
http://127.0.0.1:8000
```

## 啟動 Vue 前端

前端在 `frontend\medivector-chat-app`，使用 Vite + Vue。

```powershell
cd frontend\medivector-chat-app
npm run dev
```

前端開發伺服器預設會跑在：

```text
http://127.0.0.1:3000
```

Vite 已設定 `/api` proxy 到 Python 後端 `http://127.0.0.1:8000`。

若要讓 Python 直接服務前端靜態檔，先在 `frontend\medivector-chat-app` 執行 `npm run build`，產生 `dist` 後再開 `http://127.0.0.1:8000`。

## 重啟後端 API

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

如果 Docker app 已啟動，但 `http://localhost:8000/` 仍看到舊畫面或「前端尚未 build」，通常是本機舊的 Python server 佔著 8000。可以用 `netstat -ano | Select-String ':8000'` 找 PID，再停止舊程序後重新整理瀏覽器。

## 使用方式

### 新增資料

按左側工具列的「+新增資料」，會開啟新增資料視窗。填入：

- 來源 ID：可留空，系統會自動產生
- 標題
- 來源
- 內容，或上傳 TXT / PDF 衛教檔案

若同時填寫內容並上傳檔案，系統會把兩者合併後產生 embedding。上傳的 TXT / PDF 原始檔會保存到 MinIO，向量資料庫會記錄檔名、bucket、object key 與檔案大小。PDF 需是可複製文字的 PDF；掃描圖片型 PDF 目前不做 OCR。

若檔案文字太長，系統會自動切成多個 chunk 後分別 embedding，避免超過 OpenAI embeddings 單次輸入上限。原始檔仍只會在 MinIO 保存一份。

按「新增並 embedding」後，按鈕會鎖定並顯示 loading。成功後清單會自動刷新，且資料依建立時間由新到舊排序。

### 刪除資料

按單筆資料右上角「刪除」。刪除中會鎖定該按鈕並顯示 loading，完成後清單會重新整理。

### 問答

在右側輸入問題：

- `Enter`：送出
- `Shift+Enter`：換行

送出前可以切換「使用 RAG 搜尋向量資料庫」：

- 開啟：後端會先將當前問題 embedding，搜尋 vector DB，再把相關資料交給 GPT 回答。
- 關閉：後端不搜尋 vector DB，直接讓 GPT 依模型能力與對話上下文回答。

送出後會顯示「思考中」。

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

新增時會呼叫 OpenAI embeddings。Web 介面上傳 TXT / PDF 時會使用 `multipart/form-data`，欄位名稱為 `file`。有上傳檔案時，後端會先抽出文字做 embedding，並把原始檔保存到 MinIO bucket。

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
  "question": "年輕人健身要注意什麼？",
  "rag_enabled": true
}
```

## 環境變數

| 名稱 | 預設值 | 說明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 無 | 必填，用於 embeddings 與 GPT |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | embedding 模型 |
| `OPENAI_CHAT_MODEL` | `gpt-4.1-mini` | 回答用模型 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI API base URL |
| `TOP_K` | `5` | 最多回傳幾筆參考資料 |
| `REFERENCE_CANDIDATE_LIMIT` | `20` | vector search 第一階段先取幾筆候選 |
| `MAX_REFERENCE_DISTANCE` | `0.65` | 絕對 distance 上限 |
| `REFERENCE_DISTANCE_MARGIN` | `0.12` | 只保留最佳命中 distance 附近的參考 |
| `MEMORY_MESSAGES` | `10` | 保留最近幾則對話給 GPT |
| `MAX_EMBEDDING_CHARS` | `6000` | TXT / PDF 匯入後每個 embedding chunk 的最大字元數 |
| `WEAVIATE_HOST` | `127.0.0.1` | Weaviate HTTP host；Docker 內使用 `weaviate` |
| `WEAVIATE_PORT` | `8080` | Weaviate HTTP port |
| `WEAVIATE_GRPC_PORT` | `50051` | Weaviate gRPC port |
| `MINIO_ENDPOINT` | `127.0.0.1:9000` | MinIO API endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | `health-education-files` | 保存上傳衛教檔案的 bucket |
| `MINIO_SECURE` | `false` | 是否使用 HTTPS 連線 MinIO |
| `HOST` | `127.0.0.1` | Web app host |
| `PORT` | `8000` | Web app port |

## 檢索邏輯

目前 vector DB 搜尋只使用「當前問題」做 embedding，避免先前對話污染檢索結果。短期記憶只會交給 GPT 回答時參考。

針對常見中文衛教關鍵詞，檢索時會補上少量英文同義詞，例如「鼠蹊／腹股溝」會補 `groin / inguinal`，「神經」會補 `nerve / ilioinguinal / genitofemoral` 等。這只影響 vector DB 檢索，不會改寫使用者原本的問題。

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
