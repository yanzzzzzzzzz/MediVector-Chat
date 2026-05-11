import json
import os
import sys
import time
import traceback
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.classes.query import MetadataQuery


COLLECTION_NAME = "Article"
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
TOP_K = int(os.getenv("TOP_K", "3"))
MAX_REFERENCE_DISTANCE = float(os.getenv("MAX_REFERENCE_DISTANCE", "0.45"))
REFERENCE_DISTANCE_MARGIN = float(os.getenv("REFERENCE_DISTANCE_MARGIN", "0.04"))
MEMORY_MESSAGES = int(os.getenv("MEMORY_MESSAGES", "10"))


CONVERSATIONS: dict[str, list[dict[str, str]]] = {}


INDEX_HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Vector DB 中文問答</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f8;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #687381;
      --line: #d9dee5;
      --accent: #0f766e;
      --accent-strong: #0b5f59;
      --danger: #b42318;
      --soft: #eef7f5;
      --shadow: 0 10px 28px rgba(16, 24, 40, 0.08);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", system-ui, sans-serif;
    }

    header {
      height: 60px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 24px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }

    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0;
    }

    main {
      display: grid;
      grid-template-columns: minmax(360px, 42%) minmax(420px, 1fr);
      gap: 18px;
      padding: 18px;
      height: calc(100vh - 60px);
      min-height: 680px;
    }

    section {
      min-height: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      display: flex;
      flex-direction: column;
    }

    .toolbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
    }

    .toolbar h2 {
      margin: 0;
      font-size: 15px;
      font-weight: 700;
    }

    .actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    button {
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--ink);
      padding: 0 12px;
      font: inherit;
      font-size: 14px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }

    button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #ffffff;
    }

    button.primary:hover { background: var(--accent-strong); }
    button.danger { color: var(--danger); border-color: #f1b7b2; }
    button:disabled { opacity: 0.55; cursor: not-allowed; }

    .spinner {
      width: 14px;
      height: 14px;
      border: 2px solid rgba(255, 255, 255, 0.45);
      border-top-color: #ffffff;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      display: none;
      flex: 0 0 auto;
    }

    button.loading .spinner { display: inline-block; }

    button.danger .spinner {
      border-color: rgba(180, 35, 24, 0.25);
      border-top-color: var(--danger);
    }

    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    .status {
      color: var(--muted);
      font-size: 13px;
      min-width: 180px;
      text-align: right;
    }

    .content {
      min-height: 0;
      overflow: auto;
      padding: 14px 16px;
    }

    .doc-list {
      display: grid;
      gap: 10px;
    }

    .list-loading {
      min-height: 120px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      color: var(--muted);
      font-size: 14px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: #fbfcfd;
    }

    .list-loading .spinner {
      display: inline-block;
      border-color: rgba(15, 118, 110, 0.22);
      border-top-color: var(--accent);
    }

    .doc {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #ffffff;
    }

    .doc-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
      margin-bottom: 8px;
    }

    .doc-title {
      font-weight: 700;
      font-size: 14px;
      line-height: 1.4;
      overflow-wrap: anywhere;
    }

    .doc-meta {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }

    .doc-content {
      margin-top: 8px;
      color: #2f3a46;
      font-size: 13px;
      line-height: 1.6;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    .embedding {
      margin-top: 10px;
      border-top: 1px solid var(--line);
      padding-top: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .embedding summary {
      cursor: pointer;
      overflow-wrap: anywhere;
    }

    .embedding pre {
      max-height: 180px;
      overflow: auto;
      margin: 8px 0 0;
      padding: 10px;
      border-radius: 6px;
      background: #f4f6f8;
      color: #26323f;
      font-size: 11px;
      line-height: 1.5;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    form {
      display: grid;
      gap: 10px;
      padding: 14px 16px;
      border-top: 1px solid var(--line);
      background: #fbfcfd;
    }

    dialog {
      width: min(620px, calc(100vw - 32px));
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0;
      color: var(--ink);
      box-shadow: 0 24px 70px rgba(16, 24, 40, 0.24);
    }

    dialog::backdrop {
      background: rgba(23, 32, 42, 0.42);
    }

    .dialog-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
    }

    .dialog-head h2 {
      margin: 0;
      font-size: 16px;
    }

    .dialog-form {
      border-top: 0;
      background: #ffffff;
    }

    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      padding-top: 4px;
    }

    label {
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }

    input, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--ink);
      padding: 9px 10px;
      font: inherit;
      font-size: 14px;
      resize: vertical;
      letter-spacing: 0;
    }

    textarea { min-height: 96px; }
    .two { display: grid; grid-template-columns: 120px 1fr; gap: 10px; }

    .chat-log {
      min-height: 0;
      flex: 1;
      overflow: auto;
      padding: 16px;
      display: grid;
      align-content: start;
      gap: 12px;
    }

    .msg {
      max-width: 88%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      line-height: 1.6;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-size: 14px;
      background: #ffffff;
    }

    .msg.user {
      justify-self: end;
      background: var(--soft);
      border-color: #b8ddd7;
    }

    .msg.assistant { justify-self: start; }

    .msg.thinking {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      color: var(--muted);
    }

    .msg.thinking .spinner {
      display: inline-block;
      border-color: rgba(15, 118, 110, 0.22);
      border-top-color: var(--accent);
    }

    .refs {
      margin-top: 10px;
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .citation {
      height: auto;
      min-width: 28px;
      padding: 1px 6px;
      margin: 0 2px;
      border-color: #b8ddd7;
      background: var(--soft);
      color: var(--accent-strong);
      font-size: 12px;
      vertical-align: baseline;
      display: inline-flex;
    }

    .reference-body {
      padding: 14px 16px;
      display: grid;
      gap: 10px;
    }

    .reference-meta {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
      overflow-wrap: anywhere;
    }

    .reference-content {
      max-height: 48vh;
      overflow: auto;
      margin: 0;
      padding: 12px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #fbfcfd;
      color: #26323f;
      font: inherit;
      font-size: 14px;
      line-height: 1.7;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    .ask-form {
      grid-template-columns: 1fr auto;
      align-items: end;
    }

    .ask-form label { grid-column: 1; }
    .ask-form button { grid-column: 2; height: 42px; min-width: 88px; }
    .ask-form textarea { min-height: 42px; max-height: 150px; }

    @media (max-width: 920px) {
      main {
        height: auto;
        min-height: auto;
        grid-template-columns: 1fr;
      }

      section { min-height: 560px; }
      .two { grid-template-columns: 1fr; }
      .ask-form { grid-template-columns: 1fr; }
      .ask-form button { grid-column: 1; width: 100%; }
      .status { text-align: left; min-width: 0; }
      header { align-items: flex-start; height: auto; padding: 14px 16px; flex-direction: column; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Vector DB 中文問答</h1>
    <div class="status" id="status">準備中</div>
  </header>
  <main>
    <section>
      <div class="toolbar">
        <h2>向量資料庫</h2>
        <div class="actions">
          <button id="refreshBtn" title="重新載入資料">重新整理</button>
          <button class="primary" id="openDocDialogBtn" title="新增向量資料">+新增資料</button>
        </div>
      </div>
      <div class="content">
        <div class="doc-list" id="docList"></div>
      </div>
    </section>

    <section>
      <div class="toolbar">
        <h2>AI 問答</h2>
        <div class="actions">
          <button id="clearChatBtn" title="清除本頁對話記憶">清除對話</button>
        </div>
      </div>
      <div class="chat-log" id="chatLog"></div>
      <form class="ask-form" id="askForm">
        <label>問題
          <textarea id="question" required placeholder="問一個問題，系統會先搜尋 vector DB 當參考"></textarea>
        </label>
        <button class="primary" type="submit">送出</button>
      </form>
    </section>
  </main>

  <dialog id="docDialog">
    <div class="dialog-head">
      <h2>新增資料</h2>
      <button id="closeDocDialogBtn" type="button" title="關閉新增資料視窗">關閉</button>
    </div>
    <form class="dialog-form" id="docForm">
      <div class="two">
        <label>來源 ID
          <input id="sourceId" type="number" placeholder="自動產生" />
        </label>
        <label>標題
          <input id="title" required placeholder="例如：睡眠衛教重點" />
        </label>
      </div>
      <label>來源
        <input id="source" required placeholder="例如：內部測試資料 / sleep-guide" />
      </label>
      <label>內容
        <textarea id="content" required placeholder="輸入要放進 vector DB 的中文資料"></textarea>
      </label>
      <div class="dialog-actions">
        <button id="cancelDocDialogBtn" type="button">取消</button>
        <button class="primary" id="addDocBtn" type="submit">
          <span class="spinner" aria-hidden="true"></span>
          <span class="btn-text">新增並 embedding</span>
        </button>
      </div>
    </form>
  </dialog>

  <dialog id="referenceDialog">
    <div class="dialog-head">
      <h2 id="referenceTitle">參考資料</h2>
      <button id="closeReferenceDialogBtn" type="button" title="關閉參考資料視窗">關閉</button>
    </div>
    <div class="reference-body">
      <div class="reference-meta" id="referenceMeta"></div>
      <pre class="reference-content" id="referenceContent"></pre>
    </div>
  </dialog>

  <script>
    const docList = document.querySelector("#docList");
    const chatLog = document.querySelector("#chatLog");
    const statusEl = document.querySelector("#status");
    const docDialog = document.querySelector("#docDialog");
    const referenceDialog = document.querySelector("#referenceDialog");
    const referenceTitle = document.querySelector("#referenceTitle");
    const referenceMeta = document.querySelector("#referenceMeta");
    const referenceContent = document.querySelector("#referenceContent");
    const docForm = document.querySelector("#docForm");
    const addDocBtn = document.querySelector("#addDocBtn");
    const askForm = document.querySelector("#askForm");
    const conversationId = localStorage.getItem("conversationId") || crypto.randomUUID();
    localStorage.setItem("conversationId", conversationId);

    function setStatus(text) {
      statusEl.textContent = text;
    }

    async function api(path, options = {}) {
      const res = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
      return body;
    }

    function escapeHtml(text) {
      return String(text ?? "").replace(/[&<>"']/g, ch => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
      }[ch]));
    }

    function renderEmbedding(embedding) {
      if (!embedding || !embedding.dimension) {
        return `<details class="embedding"><summary>Embedding：無資料</summary></details>`;
      }
      const preview = `[${embedding.preview.join(", ")}${embedding.dimension > embedding.preview.length ? ", ..." : ""}]`;
      return `
        <details class="embedding">
          <summary>Embedding：${embedding.dimension} 維 · ${escapeHtml(preview)}</summary>
          <pre>${escapeHtml(JSON.stringify(embedding.values, null, 2))}</pre>
        </details>
      `;
    }

    function openReferenceDialog(ref) {
      referenceTitle.textContent = `[${ref.index}] ${ref.title || "參考資料"}`;
      referenceMeta.textContent = `來源：${ref.source || "未知"} · source_id=${ref.source_id ?? "未知"} · distance=${ref.distance_text || "未知"}`;
      referenceContent.textContent = ref.content || "";
      referenceDialog.showModal();
    }

    function renderAnswerWithCitations(text, references) {
      const refsByIndex = new Map(references.map(ref => [String(ref.index), ref]));
      return escapeHtml(text).replace(/\[(\d+)\]/g, (match, index) => {
        if (!refsByIndex.has(index)) return match;
        return `<button class="citation" type="button" data-ref-index="${escapeHtml(index)}">[${escapeHtml(index)}]</button>`;
      });
    }

    function renderDocs(docs) {
      if (!docs.length) {
        docList.innerHTML = `<div class="doc"><div class="doc-title">目前沒有資料</div><div class="doc-meta">按「+新增資料」建立第一筆向量資料。</div></div>`;
        return;
      }

      docList.innerHTML = docs.map(doc => `
        <article class="doc">
          <div class="doc-head">
            <div>
              <div class="doc-title">${escapeHtml(doc.title || "(未命名)")}</div>
              <div class="doc-meta">source_id=${escapeHtml(doc.source_id)} · ${escapeHtml(doc.source || "")}</div>
              <div class="doc-meta">created=${escapeHtml(doc.created_at || "未知")}</div>
              <div class="doc-meta">uuid=${escapeHtml(doc.uuid)}</div>
            </div>
            <button class="danger" data-delete="${escapeHtml(doc.uuid)}" title="刪除這筆資料">
              <span class="spinner" aria-hidden="true"></span>
              <span class="btn-text">刪除</span>
            </button>
          </div>
          <div class="doc-content">${escapeHtml(doc.content || "")}</div>
          ${renderEmbedding(doc.embedding)}
        </article>
      `).join("");

      docList.querySelectorAll("[data-delete]").forEach(btn => {
        btn.addEventListener("click", async () => {
          if (btn.disabled) return;
          if (!confirm("確定要刪除這筆 vector DB 資料？")) return;
          const buttonText = btn.querySelector(".btn-text");
          btn.disabled = true;
          btn.classList.add("loading");
          buttonText.textContent = "刪除中";
          try {
            setStatus("刪除中");
            await api(`/api/documents/${encodeURIComponent(btn.dataset.delete)}`, { method: "DELETE" });
            await loadDocs();
            setStatus("已刪除");
          } catch (err) {
            setStatus(err.message);
            alert(err.message);
            btn.disabled = false;
            btn.classList.remove("loading");
            buttonText.textContent = "刪除";
          }
        });
      });
    }

    function renderDocsLoading() {
      docList.innerHTML = `
        <div class="list-loading" role="status" aria-live="polite">
          <span class="spinner" aria-hidden="true"></span>
          <span>載入資料中</span>
        </div>
      `;
    }

    async function loadDocs() {
      setStatus("載入資料中");
      renderDocsLoading();
      const data = await api("/api/documents");
      renderDocs(data.documents);
      setStatus(`共有 ${data.documents.length} 筆資料`);
    }

    function addMessage(role, text, references = []) {
      const div = document.createElement("div");
      div.className = `msg ${role}`;
      if (role === "assistant" && references.length) {
        div.innerHTML = renderAnswerWithCitations(text, references);
        div.querySelectorAll("[data-ref-index]").forEach(button => {
          button.addEventListener("click", () => {
            const ref = references.find(item => String(item.index) === button.dataset.refIndex);
            if (ref) openReferenceDialog(ref);
          });
        });
      } else {
        div.textContent = text;
      }
      if (references.length) {
        const refs = document.createElement("div");
        refs.className = "refs";
        refs.innerHTML = references.map(ref =>
          `<div>[${ref.index}] ${escapeHtml(ref.source)} · ${escapeHtml(ref.title)} · distance=${escapeHtml(ref.distance_text)}</div>`
        ).join("");
        div.appendChild(refs);
      }
      chatLog.appendChild(div);
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    function addThinkingMessage() {
      const div = document.createElement("div");
      div.className = "msg assistant thinking";
      div.setAttribute("role", "status");
      div.setAttribute("aria-live", "polite");
      div.innerHTML = `
        <span class="spinner" aria-hidden="true"></span>
        <span>思考中</span>
      `;
      chatLog.appendChild(div);
      chatLog.scrollTop = chatLog.scrollHeight;
      return div;
    }

    docForm.addEventListener("submit", async event => {
      event.preventDefault();
      if (addDocBtn.disabled) return;
      const payload = {
        source_id: document.querySelector("#sourceId").value || null,
        title: document.querySelector("#title").value.trim(),
        source: document.querySelector("#source").value.trim(),
        content: document.querySelector("#content").value.trim(),
      };
      const buttonText = addDocBtn.querySelector(".btn-text");
      addDocBtn.disabled = true;
      addDocBtn.classList.add("loading");
      buttonText.textContent = "Embedding 中";
      try {
        setStatus("新增資料並產生 embedding");
        const data = await api("/api/documents", { method: "POST", body: JSON.stringify(payload) });
        docForm.reset();
        if (data.documents) {
          renderDocs(data.documents);
          setStatus(`共有 ${data.documents.length} 筆資料`);
        } else {
          await loadDocs();
        }
        docDialog.close();
        setStatus("已新增資料");
      } catch (err) {
        setStatus(err.message);
        alert(err.message);
      } finally {
        addDocBtn.disabled = false;
        addDocBtn.classList.remove("loading");
        buttonText.textContent = "新增並 embedding";
      }
    });

    document.querySelector("#openDocDialogBtn").addEventListener("click", () => {
      docDialog.showModal();
      document.querySelector("#title").focus();
    });

    document.querySelector("#closeDocDialogBtn").addEventListener("click", () => {
      if (addDocBtn.disabled) return;
      docDialog.close();
    });

    document.querySelector("#cancelDocDialogBtn").addEventListener("click", () => {
      if (addDocBtn.disabled) return;
      docDialog.close();
    });

    document.querySelector("#closeReferenceDialogBtn").addEventListener("click", () => {
      referenceDialog.close();
    });

    askForm.addEventListener("submit", async event => {
      event.preventDefault();
      const questionEl = document.querySelector("#question");
      const question = questionEl.value.trim();
      if (!question) return;
      addMessage("user", question);
      const thinkingMessage = addThinkingMessage();
      questionEl.value = "";
      setStatus("搜尋參考並詢問 GPT");
      try {
        const data = await api("/api/ask", {
          method: "POST",
          body: JSON.stringify({ conversation_id: conversationId, question }),
        });
        thinkingMessage.remove();
        addMessage("assistant", data.answer, data.references);
        setStatus(data.references.length ? `使用 ${data.references.length} 筆參考` : "未使用參考索引");
      } catch (err) {
        thinkingMessage.classList.remove("thinking");
        thinkingMessage.textContent = `發生錯誤：${err.message}`;
        setStatus(err.message);
      }
    });

    document.querySelector("#question").addEventListener("keydown", event => {
      if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
      event.preventDefault();
      askForm.requestSubmit();
    });

    document.querySelector("#refreshBtn").addEventListener("click", loadDocs);
    document.querySelector("#clearChatBtn").addEventListener("click", async () => {
      await api(`/api/conversations/${encodeURIComponent(conversationId)}`, { method: "DELETE" });
      chatLog.innerHTML = "";
      setStatus("已清除對話記憶");
    });

    loadDocs().catch(err => setStatus(err.message));
  </script>
</body>
</html>
"""


@dataclass
class Reference:
    index: int
    uuid: str
    source_id: int
    title: str
    source: str
    content: str
    distance: float | None


def require_openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("請先設定 OPENAI_API_KEY，才能新增 embedding 或詢問 GPT。")
    return api_key


def openai_post(api_key: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        response = httpx.post(
            f"{OPENAI_BASE_URL}{path}",
            headers=headers,
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"OpenAI API 回傳錯誤 {exc.response.status_code}: {exc.response.text}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"無法連線到 OpenAI API: {exc}") from exc
    return response.json()


def embed_texts(api_key: str, texts: list[str]) -> list[list[float]]:
    data = openai_post(api_key, "/embeddings", {"model": EMBEDDING_MODEL, "input": texts})
    return [item["embedding"] for item in data["data"]]


def document_embedding_text(document: dict[str, Any]) -> str:
    return f"標題：{document['title']}\n來源：{document['source']}\n內容：{document['content']}"


def flatten_vector(vector_payload: Any) -> list[float]:
    if isinstance(vector_payload, dict):
        vector_payload = next(
            (value for value in vector_payload.values() if isinstance(value, list)),
            [],
        )
    if not isinstance(vector_payload, list):
        return []
    if vector_payload and isinstance(vector_payload[0], list):
        vector_payload = vector_payload[0]
    return [float(value) for value in vector_payload]


def serialize_embedding(vector_payload: Any) -> dict[str, Any]:
    vector = flatten_vector(vector_payload)
    rounded = [round(value, 6) for value in vector]
    return {
        "dimension": len(rounded),
        "preview": rounded[:12],
        "values": rounded,
    }


def connect_client() -> weaviate.WeaviateClient:
    return weaviate.connect_to_local()


def ensure_collection(client: weaviate.WeaviateClient) -> None:
    if client.collections.exists(COLLECTION_NAME):
        return

    client.collections.create(
        name=COLLECTION_NAME,
        properties=[
            Property(name="source_id", data_type=DataType.INT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="source", data_type=DataType.TEXT),
            Property(name="content", data_type=DataType.TEXT),
        ],
        vector_config=Configure.Vectors.self_provided(
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
        ),
    )


def normalize_document(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    source = str(payload.get("source") or "").strip()
    content = str(payload.get("content") or "").strip()
    if not title or not source or not content:
        raise ValueError("標題、來源、內容都必填。")

    source_id = payload.get("source_id")
    if source_id in (None, ""):
        source_id = int(time.time())
    else:
        source_id = int(source_id)

    return {
        "source_id": source_id,
        "title": title,
        "source": source,
        "content": content,
    }


def list_documents() -> list[dict[str, Any]]:
    client = connect_client()
    try:
        ensure_collection(client)
        collection = client.collections.get(COLLECTION_NAME)
        result = collection.query.fetch_objects(
            limit=100,
            include_vector=True,
            return_metadata=MetadataQuery(creation_time=True),
        )
        documents = []
        for obj in result.objects:
            props = obj.properties
            created_at = obj.metadata.creation_time
            documents.append(
                {
                    "uuid": str(obj.uuid),
                    "source_id": props.get("source_id", ""),
                    "title": props.get("title", ""),
                    "source": props.get("source", ""),
                    "content": props.get("content", ""),
                    "created_at": created_at.isoformat() if created_at else "",
                    "embedding": serialize_embedding(obj.vector),
                }
            )
        documents.sort(key=lambda document: document["created_at"], reverse=True)
        return documents
    finally:
        client.close()


def add_document(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = require_openai_api_key()
    document = normalize_document(payload)
    vector = embed_texts(api_key, [document_embedding_text(document)])[0]

    client = connect_client()
    try:
        ensure_collection(client)
        collection = client.collections.get(COLLECTION_NAME)
        uuid = collection.data.insert(properties=document, vector=vector)
        return {"uuid": str(uuid), **document}
    finally:
        client.close()


def delete_document(uuid: str) -> dict[str, bool]:
    client = connect_client()
    try:
        ensure_collection(client)
        collection = client.collections.get(COLLECTION_NAME)
        return {"deleted": bool(collection.data.delete_by_id(uuid))}
    finally:
        client.close()


def search_references(client: weaviate.WeaviateClient, api_key: str, question: str) -> list[Reference]:
    collection = client.collections.get(COLLECTION_NAME)
    question_vector = embed_texts(api_key, [question])[0]
    result = collection.query.near_vector(
        near_vector=question_vector,
        limit=TOP_K,
        return_metadata=MetadataQuery(distance=True),
    )

    distances = [obj.metadata.distance for obj in result.objects if obj.metadata.distance is not None]
    best_distance = min(distances) if distances else None
    max_allowed_distance = MAX_REFERENCE_DISTANCE
    if best_distance is not None:
        max_allowed_distance = min(MAX_REFERENCE_DISTANCE, best_distance + REFERENCE_DISTANCE_MARGIN)

    references: list[Reference] = []
    seen_reference_keys: set[tuple[str, str, str]] = set()
    for obj in result.objects:
        distance = obj.metadata.distance
        if distance is not None and distance > max_allowed_distance:
            continue

        props = obj.properties
        reference_key = (
            str(props.get("title", "")),
            str(props.get("source", "")),
            str(props.get("content", "")),
        )
        if reference_key in seen_reference_keys:
            continue
        seen_reference_keys.add(reference_key)

        references.append(
            Reference(
                index=len(references) + 1,
                uuid=str(obj.uuid),
                source_id=int(props.get("source_id", 0) or 0),
                title=str(props.get("title", "")),
                source=str(props.get("source", "")),
                content=str(props.get("content", "")),
                distance=distance,
            )
        )
    return references


def chat_with_gpt(api_key: str, question: str, references: list[Reference], history: list[dict[str, str]]) -> str:
    if references:
        context = "\n\n".join(
            f"[{ref.index}] 來源: {ref.source} | 標題: {ref.title} | source_id: {ref.source_id}\n{ref.content}"
            for ref in references
        )
        user_content = (
            f"使用者目前問題：{question}\n\n"
            f"可用參考資料：\n{context}\n\n"
            "請根據可用參考資料回答。每個使用到的重點都要在句尾加上對應索引，例如 [1]。"
        )
    else:
        user_content = (
            f"使用者目前問題：{question}\n\n"
            "向量資料庫沒有找到足夠相關的參考資料。請直接回答，不要在回答中加任何 [1] 這類索引。"
        )

    messages = [
        {
            "role": "system",
            "content": (
                "你是使用繁體中文回答的助理。你可以參考同一個對話的短期上下文。"
                "若有向量資料庫參考，只能標註實際用到且能支持內容的索引；不要編造來源。"
                "若沒有參考資料，不要輸出任何引用索引。"
            ),
        },
        *history[-MEMORY_MESSAGES:],
        {"role": "user", "content": user_content},
    ]
    data = openai_post(
        api_key,
        "/chat/completions",
        {
            "model": CHAT_MODEL,
            "temperature": 0.2,
            "messages": messages,
        },
    )
    return data["choices"][0]["message"]["content"].strip()


def ask_question(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = require_openai_api_key()
    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("問題不可為空。")

    conversation_id = str(payload.get("conversation_id") or "default")
    history = CONVERSATIONS.setdefault(conversation_id, [])

    client = connect_client()
    try:
        ensure_collection(client)
        references = search_references(client, api_key, question)
        answer = chat_with_gpt(api_key, question, references, history)
    finally:
        client.close()

    history.extend(
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    )
    del history[:-MEMORY_MESSAGES]

    return {
        "answer": answer,
        "references": [
            {
                "index": ref.index,
                "uuid": ref.uuid,
                "source_id": ref.source_id,
                "title": ref.title,
                "source": ref.source,
                "content": ref.content,
                "distance": ref.distance,
                "distance_text": "未知" if ref.distance is None else f"{ref.distance:.4f}",
            }
            for ref in references
        ],
        "memory_messages": len(history),
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = "VectorDbChat/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_html(INDEX_HTML)
            return
        if parsed.path == "/api/documents":
            self.send_json({"documents": list_documents()})
            return
        self.send_error_json(404, "找不到路徑。")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/documents":
                document = add_document(self.read_json())
                self.send_json({"document": document, "documents": list_documents()}, status=201)
                return
            if parsed.path == "/api/ask":
                self.send_json(ask_question(self.read_json()))
                return
            self.send_error_json(404, "找不到路徑。")
        except Exception as exc:
            self.send_exception(exc)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/documents/"):
                uuid = unquote(parsed.path.removeprefix("/api/documents/"))
                self.send_json(delete_document(uuid))
                return
            if parsed.path.startswith("/api/conversations/"):
                conversation_id = unquote(parsed.path.removeprefix("/api/conversations/"))
                CONVERSATIONS.pop(conversation_id, None)
                self.send_json({"deleted": True})
                return
            self.send_error_json(404, "找不到路徑。")
        except Exception as exc:
            self.send_exception(exc)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_html(self, html: str, status: int = 200) -> None:
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def send_exception(self, exc: Exception) -> None:
        traceback.print_exc()
        status = 400 if isinstance(exc, (ValueError, json.JSONDecodeError)) else 500
        self.send_error_json(status, str(exc))

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), format % args))


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Web app running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
