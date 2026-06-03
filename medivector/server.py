import json
import mimetypes
import os
import sys
import traceback
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .config import FRONTEND_DIST_DIR, ROOT_DIR
from .conversations import delete_conversation, list_conversations, load_conversation_history
from .db import init_db
from .documents import add_documents, delete_document, infer_document_metadata, list_documents, update_document
from .qa import ask_question


class AppHandler(BaseHTTPRequestHandler):
    server_version = "VectorDbChat/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/documents":
            self.send_json({"documents": list_documents()})
            return
        if parsed.path == "/api/conversations":
            self.send_json({"conversations": list_conversations()})
            return
        if parsed.path.startswith("/api/conversations/"):
            conversation_id = unquote(parsed.path.removeprefix("/api/conversations/"))
            history = load_conversation_history(conversation_id)
            self.send_json({"messages": history})
            return
        if parsed.path.startswith("/api/"):
            self.send_error_json(404, "找不到路徑。")
            return
        self.send_static(parsed.path)
        return

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/documents/metadata-suggestions":
                self.send_json({"metadata": infer_document_metadata(self.read_document_payload())})
                return
            if parsed.path == "/api/documents":
                inserted_documents = add_documents(self.read_document_payload())
                self.send_json({"inserted": inserted_documents, "document": inserted_documents[0], "documents": list_documents()}, status=201)
                return
            if parsed.path == "/api/ask":
                self.send_json(ask_question(self.read_json()))
                return
            self.send_error_json(404, "找不到路徑。")
        except Exception as exc:
            self.send_exception(exc)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/documents/"):
                document_id = unquote(parsed.path.removeprefix("/api/documents/"))
                document = update_document(document_id, self.read_document_payload())
                self.send_json({"document": document, "documents": list_documents()})
                return
            self.send_error_json(404, "找不到路徑。")
        except Exception as exc:
            self.send_exception(exc)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/documents/"):
                document_id = unquote(parsed.path.removeprefix("/api/documents/"))
                self.send_json(delete_document(document_id))
                return
            if parsed.path.startswith("/api/conversations/"):
                conversation_id = unquote(parsed.path.removeprefix("/api/conversations/"))
                delete_conversation(conversation_id)
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

    def read_document_payload(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if content_type.lower().startswith("multipart/form-data"):
            return self.read_multipart_form(content_type)
        return self.read_json()

    def read_multipart_form(self, content_type: str) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}

        body = self.rfile.read(length)
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
        )

        payload: dict[str, Any] = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue

            filename = part.get_filename()
            data = part.get_payload(decode=True) or b""
            if filename:
                upload = {
                    "filename": filename,
                    "content_type": part.get_content_type(),
                    "data": data,
                }
                payload.setdefault("uploads", []).append(upload)
                payload["upload"] = upload
                continue

            charset = part.get_content_charset() or "utf-8"
            payload[str(name)] = data.decode(charset, errors="replace")
        return payload

    def send_static(self, request_path: str) -> None:
        if not FRONTEND_DIST_DIR.exists():
            self.send_error_json(404, "前端尚未 build。開發時請在 frontend\\medivector-chat-app 執行 npm run dev。")
            return

        relative_path = request_path.lstrip("/") or "index.html"
        target = (FRONTEND_DIST_DIR / relative_path).resolve()
        dist_root = FRONTEND_DIST_DIR.resolve()
        try:
            target.relative_to(dist_root)
        except ValueError:
            self.send_error_json(403, "拒絕存取。")
            return
        if not target.is_file():
            target = dist_root / "index.html"
        if not target.is_file():
            self.send_error_json(404, "找不到前端檔案。")
            return

        data = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
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


def _serve() -> None:
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    init_db()
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Web app running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


def main() -> None:
    reload = "--reload" in sys.argv or os.getenv("RELOAD", "").lower() in {"1", "true", "yes"}
    if reload:
        try:
            from watchfiles import run_process
        except ImportError:
            print("watchfiles 未安裝，請執行 pip install watchfiles。", file=sys.stderr)
            sys.exit(1)
        print("Auto-reload 已啟用，監聽 Python 檔案變動…")
        run_process(ROOT_DIR, target=_serve, watch_filter=lambda _c, p: p.endswith(".py"))
    else:
        _serve()
