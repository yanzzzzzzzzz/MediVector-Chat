import psycopg
from psycopg.types.json import Jsonb

from .api_auth import current_principal
from .config import MEMORY_MESSAGES


def conversation_owner():
    principal = current_principal.get()
    return principal.name if principal and principal.organization_id else None
from .db import db_connection


def list_conversations() -> list[dict]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id,
                       COALESCE(
                           (SELECT content FROM messages
                            WHERE conversation_id = c.id AND role = 'user'
                            ORDER BY created_at
                            LIMIT 1),
                           '新對話'
                       ) AS title,
                       c.created_at
                FROM conversations c
                WHERE (%s::text IS NULL OR c.owner_id = %s)
                ORDER BY c.created_at DESC
                LIMIT 50
                """,
                (conversation_owner(), conversation_owner()),
            )
            rows = cur.fetchall()
    return [
        {"id": str(row[0]), "title": row[1][:60], "created_at": row[2].isoformat()}
        for row in rows
    ]


def ensure_conversation(conn: psycopg.Connection, conversation_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (id, owner_id) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (conversation_id, conversation_owner() or ""),
        )
        if conversation_owner() is not None:
            cur.execute("SELECT 1 FROM conversations WHERE id=%s AND owner_id=%s", (conversation_id, conversation_owner()))
            if cur.fetchone() is None:
                from .knowledge import KnowledgeError
                raise KnowledgeError("Conversation belongs to another account", 403)


def load_conversation_history(conversation_id: str) -> list[dict]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content, metadata FROM messages
                WHERE conversation_id = %s
                  AND conversation_id IN (SELECT id FROM conversations WHERE (%s::text IS NULL OR owner_id=%s))
                ORDER BY created_at
                """,
                (conversation_id, conversation_owner(), conversation_owner()),
            )
            rows = cur.fetchall()
    from .knowledge import redact_inaccessible_history
    return redact_inaccessible_history([
        {
            "role": row[0],
            "content": row[1],
            **(row[2] if isinstance(row[2], dict) else {}),
        }
        for row in rows
    ])


def save_messages(conversation_id: str, new_messages: list[dict], *, on_saved=None):
    with db_connection() as conn:
        ensure_conversation(conn, conversation_id)
        with conn.cursor() as cur:
            for msg in new_messages:
                cur.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (%s, %s, %s, %s)",
                    (
                        conversation_id,
                        msg["role"],
                        msg["content"],
                        Jsonb(message_metadata(msg)),
                    ),
                )
            cur.execute(
                """
                DELETE FROM messages
                WHERE conversation_id = %s
                  AND id NOT IN (
                      SELECT id FROM messages
                      WHERE conversation_id = %s
                      ORDER BY created_at DESC
                      LIMIT %s
                  )
                """,
                (conversation_id, conversation_id, MEMORY_MESSAGES),
            )
        return on_saved(conn) if on_saved else None


def delete_conversation(conversation_id: str) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s AND (%s::text IS NULL OR owner_id=%s)",
                        (conversation_id, conversation_owner(), conversation_owner()))


def message_metadata(message: dict) -> dict:
    return {
        key: message[key]
        for key in (
            "references",
            "evidence_assessment",
            "retrieval_terms",
            "risk_assessment",
        )
        if key in message
    }
