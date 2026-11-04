import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor
import os
import json
import logging
import math
import random
import time
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .config import EMBEDDING_MODEL, OPENAI_BASE_URL


logger = logging.getLogger(__name__)


def require_openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("請先設定 OPENAI_API_KEY，才能新增 embedding 或詢問 GPT。")
    return api_key


def openai_post(
    api_key: str, path: str, payload: dict[str, Any], *,
    client: httpx.AsyncClient | None = None, max_attempts: int = 3,
    deadline_seconds: float = 60, clock=time.monotonic, sleep=None,
    jitter=random.random,
) -> dict[str, Any]:
    """Synchronous facade with an absolute, cancellable deadline for network IO."""
    if max_attempts < 1 or deadline_seconds <= 0:
        raise ValueError("Invalid retry budget")
    def run():
        return asyncio.run(_openai_post(
            api_key, path, payload, client=client, max_attempts=max_attempts,
            deadline_seconds=deadline_seconds, clock=clock, sleep=sleep, jitter=jitter,
        ))
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return run()
    # Some existing async upload handlers call synchronous domain functions.
    # A separate loop keeps the HTTP cancellation deadline effective there too.
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(run).result()


async def _openai_post(api_key, path, payload, *, client, max_attempts, deadline_seconds, clock, sleep, jitter):
    started = clock()
    deadline = started + deadline_seconds
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    owned_client = client is None
    category, status, attempts = "deadline", None, 0
    try:
        try:
            async with asyncio.timeout(deadline_seconds):
                client = client or httpx.AsyncClient()
                for attempt in range(1, max_attempts + 1):
                    remaining = deadline - clock()
                    if remaining <= 0:
                        category = "deadline"
                        break
                    attempts = attempt
                    retry_after = None
                    try:
                        response = await client.post(f"{OPENAI_BASE_URL}{path}", headers=headers,
                                                     json=payload, timeout=min(remaining, 20))
                        status = response.status_code
                        if clock() >= deadline:
                            category = "deadline"
                            break
                        if response.is_success:
                            category = "invalid_response"
                            data = response.json()
                            category = "success"
                            return data
                        category = "rate_limit" if status == 429 else "http_error"
                        if status not in {429, 500, 502, 503, 504}:
                            break
                        retry_after = retry_after_seconds(response.headers.get("Retry-After"))
                    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                        category = "timeout" if isinstance(exc, httpx.TimeoutException) else "network"
                    except httpx.HTTPError:
                        category = "permanent_transport"
                        break
                    if attempt == max_attempts:
                        break
                    delay = retry_after if retry_after is not None else min(8, 0.5 * 2 ** (attempt - 1)) + jitter() * .25
                    if delay >= deadline - clock():
                        category = "deadline"
                        break
                    wait = asyncio.sleep(delay) if sleep is None else sleep(delay)
                    if inspect.isawaitable(wait):
                        await wait
        except TimeoutError:
            category = "deadline"
        raise RuntimeError(f"OpenAI request failed: category={category}, status={status}, attempts={attempts}")
    finally:
        logger.info("openai_request %s", json.dumps({"category": category, "status": status,
                    "attempts": attempts, "retries": max(0, attempts - 1),
                    "elapsed_ms": round((clock() - started) * 1000, 2)}))
        if owned_client and client is not None:
            await client.aclose()


def retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else None
    except ValueError:
        try:
            return max(0, parsedate_to_datetime(value).timestamp() - time.time())
        except (ValueError, TypeError, OverflowError):
            return None


def embed_texts(api_key: str, texts: list[str]) -> list[list[float]]:
    data = openai_post(api_key, "/embeddings", {"model": EMBEDDING_MODEL, "input": texts})
    return [item["embedding"] for item in data["data"]]
