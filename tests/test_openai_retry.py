import asyncio
import time
import unittest
from unittest.mock import Mock

import httpx

from medivector.openai_client import openai_post, retry_after_seconds


class RetryTests(unittest.TestCase):
    def call(self, responses, **kwargs):
        self.calls = 0
        def handler(request):
            item = responses[self.calls]
            self.calls += 1
            if isinstance(item, Exception):
                raise item
            return httpx.Response(item, headers={"Retry-After": "0"}, json={"ok": True})
        self.sleep = Mock()
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            return openai_post("fake-secret", "/embeddings", {}, client=client, sleep=self.sleep, jitter=lambda: 0, **kwargs)
        finally:
            asyncio.run(client.aclose())

    def test_transient_statuses_and_transport_errors(self):
        for failure in (429, 500, 502, 503, 504, httpx.ConnectError("offline"), httpx.ReadTimeout("slow"), httpx.ReadError("reset")):
            self.assertEqual(self.call([failure, 200]), {"ok": True})
            self.assertEqual(self.calls, 2)

    def test_permanent_errors_do_not_retry(self):
        for failure in (400, 401, 403, 404):
            with self.assertRaises(RuntimeError):
                self.call([failure])
            self.assertEqual(self.calls, 1)

    def test_retry_limit_and_deadline(self):
        with self.assertRaises(RuntimeError):
            self.call([500, 500, 500])
        self.assertEqual(self.calls, 3)
        ticks = iter([0, 0, 61, 61])
        with self.assertRaisesRegex(RuntimeError, "deadline"):
            self.call([200], clock=lambda: next(ticks))
        self.assertEqual(self.calls, 1)

    def test_retry_after_exceeding_budget_does_not_wait(self):
        sleep = Mock()
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(429, headers={"Retry-After": "120"})))
        try:
            with self.assertLogs("medivector.openai_client", level="INFO") as logs:
                with self.assertRaisesRegex(RuntimeError, "deadline"):
                    openai_post("fake-secret", "/embeddings", {"sensitive": "private-question"}, client=client, deadline_seconds=1, sleep=sleep)
            sleep.assert_not_called()
            self.assertIn('"attempts": 1', logs.output[0])
            self.assertNotIn("fake-secret", str(logs.output))
            self.assertNotIn("private-question", str(logs.output))
        finally:
            asyncio.run(client.aclose())

    def test_retry_after_parsing(self):
        self.assertEqual(retry_after_seconds("12"), 12)
        self.assertEqual(retry_after_seconds("-2"), 0)
        self.assertIsNone(retry_after_seconds("invalid"))
        self.assertIsNone(retry_after_seconds("nan"))


class AbsoluteDeadlineTests(unittest.TestCase):
    def test_deadline_cancels_inflight_request(self):
        async def slow(request):
            await asyncio.sleep(10)
            return httpx.Response(200, json={"ok": True})
        client = httpx.AsyncClient(transport=httpx.MockTransport(slow))
        started = time.monotonic()
        try:
            with self.assertRaisesRegex(RuntimeError, "deadline"):
                openai_post("fake", "/embeddings", {}, client=client, deadline_seconds=.02)
            self.assertLess(time.monotonic() - started, 1)
        finally:
            asyncio.run(client.aclose())

    def test_facade_works_inside_existing_event_loop(self):
        async def run():
            client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True})))
            try:
                return openai_post("fake", "/embeddings", {}, client=client)
            finally:
                await client.aclose()
        self.assertEqual(asyncio.run(run()), {"ok": True})
