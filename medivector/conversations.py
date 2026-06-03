import psycopg

from .config import MEMORY_MESSAGES
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
                ORDER BY c.created_at DESC
                LIMIT 50
                """,
            )
            rows = cur.fetchall()
    return [
        {"id": str(row[0]), "title": row[1][:60], "created_at": row[2].isoformat()}
        for row in rows
    ]


def ensure_conversation(conn: psycopg.Connection, conversation_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
            (conversation_id,),
        )


def load_conversation_history(conversation_id: str) -> list[dict[str, str]]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content FROM messages
                WHERE conversation_id = %s
                ORDER BY created_at
                """,
                (conversation_id,),
            )
            rows = cur.fetchall()
    return [{"role": row[0], "content": row[1]} for row in rows]


def save_messages(conversation_id: str, new_messages: list[dict[str, str]]) -> None:
    with db_connection() as conn:
        ensure_conversation(conn, conversation_id)
        with conn.cursor() as cur:
            for msg in new_messages:
                cur.execute(
                    "INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)",
                    (conversation_id, msg["role"], msg["content"]),
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


def delete_conversation(conversation_id: str) -> None:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
