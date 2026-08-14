"""Read-only Streamable HTTP MCP transport for Moomoo market data.

This module deliberately implements only MCP discovery and ``tools/call`` for
quote retrieval. It never calls trading/order tools.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Mapping

import httpx

from .moomoo import MoomooAdapterError, MoomooMarketData


class MoomooMCPTransport:
    """Minimal Streamable HTTP MCP client for read-only quote discovery."""

    def __init__(self, url: str | None = None, access_token: str | None = None) -> None:
        self.url = (url or os.getenv("MOOMOO_MCP_URL", "https://mcp.moomoo.com/mcp")).strip()
        self.access_token = (access_token or os.getenv("MOOMOO_MCP_ACCESS_TOKEN", "")).strip()
        if not self.url:
            raise MoomooAdapterError("MOOMOO_MCP_URL is empty.")
        if not self.access_token:
            raise MoomooAdapterError(
                "MOOMOO_MCP_ACCESS_TOKEN is not configured. Complete Moomoo MCP OAuth "
                "in a supported MCP client and store the resulting access token as a secret."
            )
        self._session_id: str | None = None
        self._request_id = 0
        self._tools: list[Mapping[str, Any]] | None = None

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    @staticmethod
    def _decode_response(response: httpx.Response) -> Mapping[str, Any]:
        session_id = response.headers.get("Mcp-Session-Id")
        payload: Any
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            payload = None
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    data = line[5:].strip()
                    if data and data != "[DONE]":
                        payload = json.loads(data)
            if payload is None:
                raise MoomooAdapterError("Moomoo MCP returned an empty SSE response.")
        else:
            payload = response.json()
        if not isinstance(payload, Mapping):
            raise MoomooAdapterError("Moomoo MCP returned an unexpected response payload.")
        if session_id:
            payload = dict(payload)
            payload["_session_id"] = session_id
        return payload

    def _rpc(self, method: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        self._request_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": dict(params or {}),
        }
        try:
            response = httpx.post(self.url, headers=self._headers(), json=body, timeout=30.0)
            response.raise_for_status()
            result = self._decode_response(response)
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise MoomooAdapterError(f"Moomoo MCP request failed: {exc}") from exc

        if "_session_id" in result:
            self._session_id = str(result["_session_id"])
        if result.get("error"):
            raise MoomooAdapterError(f"Moomoo MCP error: {result['error']}")
        return result

    def _initialize(self) -> None:
        if self._session_id:
            return
        self._rpc(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "ai-henge-fund", "version": "0.1.0"},
            },
        )
        self._rpc("notifications/initialized", {})

    def _list_tools(self) -> list[Mapping[str, Any]]:
        if self._tools is None:
            self._initialize()
            result = self._rpc("tools/list", {})
            tools = result.get("result", {}).get("tools", [])
            if not isinstance(tools, list):
                raise MoomooAdapterError("Moomoo MCP returned an invalid tools list.")
            self._tools = [tool for tool in tools if isinstance(tool, Mapping)]
        return self._tools

    @staticmethod
    def _quote_tool(tools: list[Mapping[str, Any]]) -> Mapping[str, Any]:
        candidates: list[tuple[int, Mapping[str, Any]]] = []
        blocked = ("order", "trade", "cancel", "modify", "place", "sell", "buy")
        preferred = ("quote", "snapshot", "stock quote", "market quote", "price")
        for tool in tools:
            name = str(tool.get("name", "")).lower()
            description = str(tool.get("description", "")).lower()
            text = f"{name} {description}"
            if any(word in text for word in blocked):
                continue
            score = sum(3 for word in preferred if word in text)
            if score:
                candidates.append((score, tool))
        if not candidates:
            raise MoomooAdapterError("No read-only Moomoo quote tool was discovered.")
        candidates.sort(key=lambda item: (-item[0], str(item[1].get("name", ""))))
        return candidates[0][1]

    @staticmethod
    def _arguments(tool: Mapping[str, Any], symbol: str) -> dict[str, Any]:
        schema = tool.get("inputSchema") or {}
        properties = schema.get("properties", {}) if isinstance(schema, Mapping) else {}
        if not isinstance(properties, Mapping):
            properties = {}
        args: dict[str, Any] = {}
        for name, spec in properties.items():
            key = str(name).lower()
            if key in {"symbol", "ticker", "stock", "security", "code"}:
                args[str(name)] = symbol if "." in symbol else f"US.{symbol}"
                break
        if not args:
            required = schema.get("required", []) if isinstance(schema, Mapping) else []
            if required:
                args[str(required[0])] = symbol if "." in symbol else f"US.{symbol}"
        return args

    def get_quote(self, symbol: str) -> Mapping[str, Any]:
        """Discover and invoke one read-only quote tool for ``symbol``."""
        tools = self._list_tools()
        tool = self._quote_tool(tools)
        name = str(tool.get("name", ""))
        arguments = self._arguments(tool, symbol.strip().upper())
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        content = result.get("result", {}).get("content", [])
        if not content:
            raise MoomooAdapterError(f"Moomoo MCP quote tool {name!r} returned no content.")

        for item in content:
            if not isinstance(item, Mapping):
                continue
            text = item.get("text")
            if isinstance(text, str):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, Mapping):
                        return parsed
                except json.JSONDecodeError:
                    continue

        if isinstance(content[0], Mapping):
            return dict(content[0])
        raise MoomooAdapterError(f"Moomoo MCP quote tool {name!r} returned unsupported content.")


def build_moomoo_market_data() -> MoomooMarketData:
    """Build the read-only facade when MCP credentials are configured."""
    enabled = os.getenv("MOOMOO_MCP_ENABLED", "false").strip().lower() == "true"
    if not enabled:
        return MoomooMarketData(enabled=False)
    return MoomooMarketData(transport=MoomooMCPTransport(), enabled=True)
