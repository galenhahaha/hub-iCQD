"""Exercise the Bocha contract using an in-memory HTTP transport."""

import json
import unittest
from unittest.mock import patch

import httpx

from backend import config, tools


class SearchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.enterContext(patch.object(config, "BOCHA_API_KEY", "offline-placeholder"))
        self.enterContext(patch.object(config, "BOCHA_SEARCH_COUNT", 10))
        self.enterContext(patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")))

    async def search_with(self, handler, query="研究主题"):
        client_type = httpx.AsyncClient
        with patch.object(
            tools.httpx,
            "AsyncClient",
            side_effect=lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs),
        ):
            return await tools.web_search(query)

    async def test_request_and_normalized_results(self) -> None:
        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), tools.BOCHA_SEARCH_URL)
            self.assertEqual(request.headers["Authorization"], "Bearer offline-placeholder")
            self.assertIn("application/json", request.headers["Content-Type"])
            self.assertEqual(json.loads(request.content), {"query": "研究主题", "summary": True, "count": 10})
            return httpx.Response(200, json={"code": 200, "data": {"webPages": {"value": [
                {"url": " https://example.com/a ", "name": "来源甲", "snippet": "摘" * 600,
                 "summary": "备用摘要", "siteName": "站点", "datePublished": "2026-09-01"},
                {"url": "https://example.com/b", "summary": "备用摘要", "dateLastCrawled": "2026-09-02"},
                {"url": "https://example.com/c", "name": None, "snippet": None},
                {"url": " "}, {"name": "缺少 URL"}, None,
            ]}}})

        results = await self.search_with(handler, " 研究主题 ")
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0], {
            "url": "https://example.com/a", "title": "来源甲", "snippet": "摘" * 500,
            "site_name": "站点", "date": "2026-09-01",
        })
        self.assertEqual(results[1]["snippet"], "备用摘要")
        self.assertEqual(results[1]["date"], "2026-09-02")
        self.assertEqual(results[2]["title"], "")
        self.assertEqual(results[2]["snippet"], "")

    async def test_empty_search_responses(self) -> None:
        for payload in ({}, {"data": None}, {"data": {"webPages": None}},
                        {"data": {"webPages": {"value": []}}}):
            with self.subTest(payload=payload):
                self.assertEqual(await self.search_with(lambda request: httpx.Response(200, json=payload)), [])

    async def test_http_and_business_errors_propagate(self) -> None:
        for status, payload, error in (
            (401, {}, httpx.HTTPStatusError),
            (503, {}, httpx.HTTPStatusError),
            (200, {"code": 403, "message": "unauthorized"}, RuntimeError),
        ):
            with self.subTest(status=status, payload=payload):
                with self.assertRaises(error):
                    await self.search_with(lambda request: httpx.Response(status, json=payload))

    async def test_timeout_propagates(self) -> None:
        def handler(request):
            raise httpx.ReadTimeout("offline timeout", request=request)

        with self.assertRaises(httpx.ReadTimeout):
            await self.search_with(handler)

    async def test_invalid_payload_is_rejected(self) -> None:
        for payload in ([], {"data": "bad"}, {"data": {"webPages": "bad"}},
                        {"data": {"webPages": {"value": "bad"}}}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    await self.search_with(lambda request: httpx.Response(200, json=payload))
        with self.assertRaises(ValueError):
            await self.search_with(lambda request: httpx.Response(200, content=b"invalid json"))

    async def test_empty_query_and_missing_key_do_not_create_client(self) -> None:
        with patch.object(config, "BOCHA_API_KEY", ""), patch.object(tools.httpx, "AsyncClient") as client:
            self.assertEqual(await tools.web_search("  "), [])
            with self.assertRaisesRegex(ValueError, "BOCHA_API_KEY"):
                await tools.web_search("主题")
            client.assert_not_called()

    async def test_invalid_count_does_not_create_client(self) -> None:
        with patch.object(config, "BOCHA_SEARCH_COUNT", 0), patch.object(tools.httpx, "AsyncClient") as client:
            with self.assertRaisesRegex(ValueError, "BOCHA_SEARCH_COUNT"):
                await tools.web_search("主题")
            client.assert_not_called()
