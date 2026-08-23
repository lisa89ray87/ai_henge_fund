from __future__ import annotations

import json

import httpx

from ai_henge_fund.market_data.moomoo import MoomooMarketData
from ai_henge_fund.market_data.moomoo_mcp import MoomooMCPTransport


def test_mcp_transport_discovers_quote_tool_and_normalizes(monkeypatch) -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        method = body["method"]
        if method == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": body["id"], "result": {"protocolVersion": "2025-03-26"}},
                headers={"Mcp-Session-Id": "test-session"},
            )
        if method == "notifications/initialized":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}})
        if method == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "get_stock_quote",
                                "description": "Get a read-only real-time stock quote",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"symbol": {"type": "string"}},
                                    "required": ["symbol"],
                                },
                            },
                            {
                                "name": "place_order",
                                "description": "Place an order",
                                "inputSchema": {"type": "object"},
                            },
                        ]
                    },
                },
            )
        if method == "tools/call":
            assert body["params"]["name"] == "get_stock_quote"
            assert body["params"]["arguments"] == {"symbol": "US.AAPL"}
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps({"last_price": 123.45, "volume": 1000})}
                        ]
                    },
                },
            )
        raise AssertionError(f"unexpected method {method}")

    transport = httpx.MockTransport(handler)
    original_post = httpx.post

    def fake_post(url, **kwargs):
        request = httpx.Request(
            "POST",
            url,
            headers=kwargs.get("headers"),
            content=json.dumps(kwargs.get("json")).encode(),
        )
        response = transport.handle_request(request)
        response.request = request
        return response

    monkeypatch.setattr(httpx, "post", fake_post)

    mcp = MoomooMCPTransport(url="https://example.test/mcp", access_token="test-token")
    quote = MoomooMarketData(transport=mcp, enabled=True).get_quote("AAPL")

    assert quote.symbol == "US.AAPL"
    assert quote.last_price == 123.45
    assert quote.volume == 1000
    assert [call["method"] for call in calls] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]

    monkeypatch.setattr(httpx, "post", original_post)
