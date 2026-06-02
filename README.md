# Vector DB 中文問答 Demo

這是一個本機執行的中文衛教 RAG 測試專案。它使用 PostgreSQL + pgvector 作為 vector DB，OpenAI embeddings 產生向量，並用 GPT 根據搜尋到的參考資料回答問題。

## 功能

- 查看目前 PostgreSQL / pgvector 裡的中文衛教資料
- 新增資料時自動呼叫 OpenAI embedding，並寫入 vector DB
- 新增資料可直接輸入文字，或上傳 TXT / PDF 衛教檔案
- 上傳的 TXT / PDF 原始檔會保存到 MinIO
- 刪除單筆 vector DB 資料
- 問答時先搜尋 vector DB，再把參考資料交給 GPT
- AI 問答可切換是否使用 RAG 搜尋，方便比較有無引用資料的差異
- 回答中會標記實際使用的參考來源，例如 `[1]`
- 回答中的 `[1]`、`[2]` 可點擊查看原始參考資料
- 沒有足夠相關參考時，不會在回答中加索引
- 對話會保存到 PostgreSQL，左側可切換、刪除不同對話
- 同一對話保留最近 10 則訊息作短期記憶
- AI 回答會顯示證據充足度、檢索詞與醫療風險分級
- 紅燈急症風險會轉向就醫/急救提醒，不進入一般衛教回答
- Enter 送出問題，Shift+Enter 換行
- 新增、刪除、載入資料、AI 思考中都有 loading 狀態
- 每筆資料可查看 embedding 維度、前段預覽與完整數字 array
- 每次問答的參考來源會顯示 distance

## 檔案

- `app.py`：Web app 後端、OpenAI 呼叫、PostgreSQL / pgvector 操作，並在 production 服務 Vue build 後的靜態檔
- `frontend/medivector-chat-app`：Vue / Vite 前端專案
- `test.py`：舊版 CLI 測試稿，主流程以 `app.py` 為準
- `docker-compose.yml`：啟動 app、PostgreSQL / pgvector 與 MinIO
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

`.env` 會被 Git 忽略，不會提交到 repository。Docker Compose 會自動讀取 `.env`；本機執行 `app.py` 時也會載入同一份 `.env`。

## 啟動 PostgreSQL / pgvector 與 MinIO

在專案目錄執行：

```powershell
docker compose up -d
```

確認狀態：

```powershell
docker compose ps
```

PostgreSQL 預設會跑在：

```text
127.0.0.1:5432
```

PostgreSQL 預設連線資訊：

```text
database: medivector
user: medivector
password: medivector
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
- `postgres`：PostgreSQL + pgvector，`127.0.0.1:5432`
- `minio`：原始檔保存，API `http://127.0.0.1:9000`，Console `http://127.0.0.1:9001`

啟動後請開：

```text
http://localhost:8000/
```

`http://localhost:8000/` 是前端頁面；PostgreSQL 是資料庫服務，不會像一般網頁一樣用瀏覽器開啟。

查看狀態：

```powershell
docker compose ps
```

停止服務：

```powershell
docker compose down
```

## 啟動後端 API

請先確認 PostgreSQL / pgvector 與 MinIO 已透過 Docker Compose 啟動。

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

### 取得對話列表

```http
GET /api/conversations
```

回傳已保存的對話，標題會使用該對話第一則使用者訊息。

### 取得單一對話記錄

```http
GET /api/conversations/{conversation_id}
```

### 刪除對話

```http
DELETE /api/conversations/{conversation_id}
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
| `MIN_REFERENCE_COUNT` | `2` | 判定證據充足時至少需要幾筆參考 |
| `MAX_EVIDENCE_DISTANCE` | 同 `MAX_REFERENCE_DISTANCE` | 判定證據充足時可接受的最佳 distance 上限 |
| `MEMORY_MESSAGES` | `10` | 保留最近幾則對話給 GPT |
| `MAX_EMBEDDING_CHARS` | `6000` | TXT / PDF 匯入後每個 embedding chunk 的最大字元數 |
| `PG_HOST` | `127.0.0.1` | PostgreSQL host；Docker app 內使用 `postgres` |
| `PG_PORT` | `5432` | PostgreSQL port |
| `PG_USER` | `medivector` | PostgreSQL 使用者 |
| `PG_PASSWORD` | `medivector` | PostgreSQL 密碼 |
| `PG_DATABASE` | `medivector` | PostgreSQL database |
| `MINIO_ENDPOINT` | `127.0.0.1:9000` | MinIO API endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | `health-education-files` | 保存上傳衛教檔案的 bucket |
| `MINIO_SECURE` | `false` | 是否使用 HTTPS 連線 MinIO |
| `HOST` | `127.0.0.1` | Web app host |
| `PORT` | `8000` | Web app port |

## 檢索邏輯

目前 vector DB 搜尋會使用「當前問題」加上 AI 產生的中英文檢索詞做 embedding。短期記憶只會交給 GPT 回答時參考，不會直接把整段歷史對話塞進向量檢索。

針對中文衛教問題，系統會先用小模型產生 3 到 8 組適合檢索的中英文詞組，例如症狀、解剖部位、疾病名稱與醫學術語。這只影響 vector DB 檢索，不會改寫使用者原本的問題。

搜尋後會做兩層過濾：

1. distance 不可超過 `MAX_REFERENCE_DISTANCE`
2. distance 不可超過「最佳命中 distance + `REFERENCE_DISTANCE_MARGIN`」

因此如果最佳命中是年輕人健身，距離明顯比較遠的高血壓資料會被排除。

搜尋結果也會再進行證據充足度評估：

1. 參考資料數量需達到 `MIN_REFERENCE_COUNT`
2. 最佳 distance 需低於 `MAX_EVIDENCE_DISTANCE`

若證據不足，回答會降低語氣強度，避免把推測講成確定結論。

## Embedding 與 Distance 視覺化

左側每筆資料會顯示 embedding 摘要：

- 維度數，例如 `1536 維`
- 前 12 個浮點數作預覽
- 展開後可查看完整 embedding array

右側 GPT 回答下方的參考來源會顯示：

- `distance`：pgvector cosine distance，越低代表越相似
- 證據狀態：目前引用是否達到數量與距離門檻
- 檢索詞：本次用於擴展向量檢索的詞組
- 風險分級：一般、注意或急症

## 注意事項

- `app.py` 啟動時只會建立缺少的 PostgreSQL extension、資料表與索引，不會清空既有資料。
- 使用 Docker Compose 時，PostgreSQL 與 MinIO 資料會保存在 Docker volume。
- `test.py` 是舊版 Weaviate CLI 測試稿，和目前 Docker Compose 的 PostgreSQL / pgvector 主流程不同。
- 問答引用時會對內容相同的參考資料做去重，避免重複列出相同來源。
