import sys
import time
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector

from .config import EMBEDDING_DIM, PG_DATABASE, PG_HOST, PG_PASSWORD, PG_PORT, PG_USER


def get_pg_conninfo() -> str:
    return f"host={PG_HOST} port={PG_PORT} user={PG_USER} password={PG_PASSWORD} dbname={PG_DATABASE}"


@contextmanager
def db_connection():
    conn = psycopg.connect(get_pg_conninfo())
    register_vector(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    max_retries = 10
    # Step 1: 建立 extension（不需要 vector type，用普通連線）
    for attempt in range(max_retries):
        try:
            conn = psycopg.connect(get_pg_conninfo())
            try:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
                conn.commit()
            finally:
                conn.close()
            break
        except Exception as exc:
            if attempt < max_retries - 1:
                print(f"DB 連線失敗（{attempt + 1}/{max_retries}），3 秒後重試…: {exc}", file=sys.stderr)
                time.sleep(3)
            else:
                raise

    # Step 2: 建立資料表（extension 已存在，可安全 register_vector）
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS articles (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    document_id UUID NOT NULL DEFAULT gen_random_uuid(),
                    source_id BIGINT NOT NULL DEFAULT 0,
                    title TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    publisher TEXT NOT NULL DEFAULT '',
                    published_date TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT '',
                    audience TEXT NOT NULL DEFAULT '',
                    topic TEXT NOT NULL DEFAULT '',
                    credibility TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    file_name TEXT NOT NULL DEFAULT '',
                    file_object_key TEXT NOT NULL DEFAULT '',
                    file_bucket TEXT NOT NULL DEFAULT '',
                    file_content_type TEXT NOT NULL DEFAULT '',
                    file_size BIGINT NOT NULL DEFAULT 0,
                    chunk_index INT NOT NULL DEFAULT 1,
                    chunk_count INT NOT NULL DEFAULT 1,
                    embedding VECTOR({EMBEDDING_DIM}),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS document_id UUID")
            cur.execute("UPDATE articles SET document_id = id WHERE document_id IS NULL")
            cur.execute("ALTER TABLE articles ALTER COLUMN document_id SET DEFAULT gen_random_uuid()")
            cur.execute("ALTER TABLE articles ALTER COLUMN document_id SET NOT NULL")
            for column_name in (
                "publisher",
                "published_date",
                "version",
                "audience",
                "topic",
                "credibility",
            ):
                cur.execute(f"ALTER TABLE articles ADD COLUMN IF NOT EXISTS {column_name} TEXT NOT NULL DEFAULT ''")
            cur.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS articles_embedding_idx
                ON articles USING hnsw (embedding vector_cosine_ops)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS articles_document_id_idx
                ON articles (document_id, chunk_index)
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS articles_topic_idx
                ON articles (topic)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id UUID PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS messages_conv_idx
                ON messages (conversation_id, created_at)
            """)
