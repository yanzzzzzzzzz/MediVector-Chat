# Vector DB 中文問答 Demo

這是一個本機執行的中文衛教 RAG 測試專案。它使用 PostgreSQL + pgvector 作為 vector DB，OpenAI embeddings 產生向量，並用 GPT 根據搜尋到的參考資料回答問題。

## 功能

- 查看目前 PostgreSQL / pgvector 裡的中文衛教資料
- 衛教資料庫可用關鍵字搜尋，並依發布日期區間篩選
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

目前 vector DB 搜尋會先用 AI 進行 query contextualization：判斷當前問題是否需要最近對話才能理解，並產生一個可獨立檢索的 standalone question。每次問答都會重新產生 standalone question 與中英文檢索詞，避免同一對話後續問題沿用上一題的檢索詞。若問題本身已有明確主題，例如「心臟跳動異常怎麼辦」，檢索會以該主題為準，不應把最近對話中的其他疾病混入；若問題是語意不完整的追問，才會用最近對話補全 standalone question。短期記憶仍會交給 GPT 回答時參考，但不會直接把整段歷史對話塞進向量檢索。

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

## 純 Retrieval 評估 API

`POST /api/retrieval/search` 不產生答案、不評估急症、不讀寫對話。
OpenAPI schema 位於 `/docs`。參數 `retrieval_terms` 可重播已保存的詞組（最多 8 組），
避免比較不同策略時重複改寫；若同時啟用 query_expansion，則使用新的改寫輸出。範例：

```sh
curl http://127.0.0.1:8000/api/retrieval/search \
  -H 'Content-Type: application/json' \
  -d '{"question":"睡眠不足怎麼辦","top_k":10,"candidate_limit":20,"mode":"raw","query_expansion":false}'
```

- `mode=raw`：依向量距離回傳前 K 筆，不套用 distance 門檻或去重。
- `mode=filtered`（預設）：依 `max_distance`、`distance_margin`、`dedup` 過濾再取前 K 筆；預設沿用聊天設定。
- `candidate_limit` 實際使用值至少為 `top_k`；兩者上限 1000。
- `query_expansion=false`（預設）只呼叫 embedding；啟用時另呼叫查詢改寫模型，沒有聊天歷史。
- 回應包含 `document_id`、`chunk_id`（articles.id）、`rank`、`raw_rank`、distance、content、實際 query/terms、耗時與設定。Filtered rank 會重新編號，raw_rank 保留候選排名。
- `elapsed_ms` 包含查詢改寫、embedding、資料庫查詢與過濾，不包含 HTTP 傳輸。

未設定 `RETRIEVAL_API_TOKEN` 時只接受 loopback peer；設定後所有請求都需
`Authorization: Bearer <token>`。透過 Docker port mapping 或反向代理呼叫時應設定 token。
`python app.py` 停用 forwarded header 信任；自行啟動 Uvicorn 時也應使用
`--no-proxy-headers`，避免將代理提供的位址當作授權依據。
此限制只保護純檢索端點，既有其他 API 仍屬本機 Demo，不應直接公開。

比較 Top-K 或過濾策略時，應固定 query expansion 輸出、embedding model、corpus
及索引版本。回應設定不代表 corpus 快照；測試端需另行保存資料庫版本。

離線測試（不需要 OpenAI Key 或執行中的資料庫）：

```sh
python -m unittest discover -s tests -v
```

## API 安全與部署邊界

預設未設定 `API_USERS` 時，所有 API 僅接受 loopback peer。Docker Compose 對外 port
綁定 `127.0.0.1`；Docker 容器收到的 peer 通常是 bridge gateway，因此使用 Docker 前
請設定 `API_USERS`，再於頁面上方輸入 Token。Token 只存在該分頁的 sessionStorage。

`API_USERS` 是 JSON object，key 為穩定帳號 ID，value 包含 `role` 和 `token`：

```dotenv
API_USERS={"alice":{"role":"admin","token":"替換為至少32個ASCII字元的隨機Token"},"bob":{"role":"user","token":"替換為另一個至少32字元的隨機Token"}}
```

請用密碼管理器或 `python -c 'import secrets; print(secrets.token_urlsafe(32))'` 產生 Token，
不要直接使用上述範例文字。設定後重啟服務；每個請求須帶 `Authorization: Bearer <token>`。
`admin` 能新增／編輯／刪除自己命名空間的文件，`user` 能檢索自己的文件並操作自己的對話。
可先以 admin 匯入資料後將同一帳號降為 user；帳號 ID 不變就沿用同一份資料。
admin 也無法透過 API 讀取其他帳號的資料。

各帳號的 articles/conversations/messages 存在獨立 PostgreSQL schema，查詢不會回退到
public tables。舊 Demo 資料留在 public，不會自動搬移或指派給任何帳號。開啟授權模式後
看不到舊資料是預期行為；資料搬移必須先明確確認擁有者並備份。更換 token 保留資料，
更換帳號 ID 會建立新命名空間。資料庫憑證為服務端秘密，不提供給一般使用者。

`RETRIEVAL_API_TOKEN` 可單獨授權只讀評估端點存取 legacy public corpus；設定 API_USERS
時以帳號 Token 為準。其他 API 不接受這個評估 Token。
`API_RATE_LIMIT_PER_MINUTE` 預設 120，為單程序記憶體限流；多個 worker 或正式部署需在
入口加共享限流、HTTPS 與適當身分服務。`MAX_REQUEST_BYTES` 預設 10 MiB，包含 multipart
開銷，超過回 413。上傳格式仍限 TXT/PDF；未授權回 401，權限不足回 403。

## RAG 實驗與診斷

[evaluation/README.md](evaluation/README.md) 提供分塊 manifest、版本化實驗索引、
Exact/HNSW benchmark、引用標註檢查與 Retrieval 匯出指令。它們是獨立 Evaluation Lab 的
資料介面與小型診斷工具，沒有把 .NET Benchmark 平台嵌入此專案。

畫面的「檢索證據估計」僅依 count/distance 判定，**沒有驗證答案正確性或引用支持關係**。
Generation faithfulness 與 Retrieval quality 必須分開評估。
OpenAI 呼叫最多嘗試三次，僅對網路錯誤、429、500/502/503/504 重試，採 backoff/jitter，
尊重 Retry-After，並在 60 秒預算耗盡後停止嘗試。每次 HTTP 呼叫最多 20 秒 inactivity timeout，
外層另以可取消的 async deadline 限制每次外部呼叫整體 60 秒（含重試等待）；這不是完整問答的總時間上限。每次外部呼叫記錄 category/status/attempts/retries/elapsed_ms，
不記錄問題內容、API Key 或服務端錯誤本文。開啟 Python INFO logging 可收集這些診斷。

逐項實作與待辦：[GitHub issue 處理紀錄](evaluation/ISSUE_STATUS.md)。


## 院所文件與正式檢索（#13–#15）

新增 `/knowledge` 文件管理頁與 `/api/knowledge` API。院所帳號透過 `API_USERS` 設定穩定的
`organization_id`、`branch_ids`、`department_ids`；同機構共用來源文件，個人對話仍依擁有者隔離。
新增角色 `nurse` 與 `reviewer`：護理人員建立待審版本，審核者核准／退回／撤回；Admin 管理院區科別名稱。

既有資料只會遷移為 **Draft**，不會自動核准。新修訂保留原版本，正式查詢只使用符合院區、科別、
ACL 與有效期間的核准版本；沒有來源時直接回覆無法確認院所規範，不呼叫答案模型補寫。
院所帳號不使用舊 `/api/documents` 路徑，避免繞過版本治理。匯入格式目前為文字，PDF 附件工作流仍待補齊。

[資料關係、角色設定、狀態機、API 與操作說明](docs/knowledge-governance.md)。
這一階段是來源文件的審核與檢索；產生衛教草稿後的獨立人工審核／發布流程（#17）、完整品質規則及
Release Gate（#18/#19）仍未完成，亦未進行真人 Pilot（#20）。
