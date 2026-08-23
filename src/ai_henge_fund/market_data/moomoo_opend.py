"""Read-only adapter for the local Moomoo OpenD quote service."""

from __future__ import annotations

import os
from typing import Any, Mapping

from .moomoo import MoomooAdapterError


class MoomooOpenDTransport:
    """Translate normalized read-only calls into the official Moomoo Python SDK."""

    _INTERVALS = {
        "1m": "K_1M",
        "5m": "K_5M",
        "15m": "K_15M",
        "30m": "K_30M",
        "60m": "K_60M",
        "1d": "K_DAY",
        "1w": "K_WEEK",
        "1mo": "K_MON",
    }

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or os.getenv("MOOMOO_OPEND_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("MOOMOO_OPEND_PORT", "11111"))
        self._quote_ctx: Any | None = None

    def _context(self) -> Any:
        if self._quote_ctx is not None:
            return self._quote_ctx
        try:
            from moomoo import OpenQuoteContext
        except ImportError as exc:
            raise MoomooAdapterError("The official moomoo-api package is not installed.") from exc
        try:
            self._quote_ctx = OpenQuoteContext(host=self.host, port=self.port)
        except Exception as exc:
            raise MoomooAdapterError(
                f"Unable to connect to Moomoo OpenD at {self.host}:{self.port}: {exc}"
            ) from exc
        return self._quote_ctx

    @staticmethod
    def _row(frame: Any) -> Mapping[str, Any]:
        if frame is None or len(frame) == 0:
            raise MoomooAdapterError("Moomoo OpenD returned no market-data rows.")
        return frame.iloc[0].to_dict()

    def get_quote(self, symbol: str) -> Mapping[str, Any]:
        ctx = self._context()
        try:
            from moomoo import RET_OK, SubType
            ret_sub, message = ctx.subscribe([symbol], [SubType.QUOTE], subscribe_push=False)
            if ret_sub != RET_OK:
                raise MoomooAdapterError(f"Quote subscription failed for {symbol}: {message}")
            ret, data = ctx.get_stock_quote([symbol])
        except MoomooAdapterError:
            raise
        except Exception as exc:
            raise MoomooAdapterError(f"Moomoo quote request failed for {symbol}: {exc}") from exc
        if ret != RET_OK:
            raise MoomooAdapterError(f"Moomoo quote request failed for {symbol}: {data}")
        return self._row(data)

    def get_candles(self, symbol: str, num: int, interval: str) -> list[Mapping[str, Any]]:
        ctx = self._context()
        try:
            from moomoo import AuType, KLType, RET_OK, SubType
            ktype_name = self._INTERVALS.get(interval.lower())
            if ktype_name is None:
                raise ValueError(f"Unsupported candle interval: {interval}")
            ktype = getattr(KLType, ktype_name)
            ret_sub, message = ctx.subscribe([symbol], [ktype], subscribe_push=False)
            if ret_sub != RET_OK:
                raise MoomooAdapterError(f"Candle subscription failed for {symbol}: {message}")
            ret, data = ctx.get_cur_kline(symbol, num, ktype, AuType.QFQ)
        except MoomooAdapterError:
            raise
        except Exception as exc:
            raise MoomooAdapterError(f"Moomoo candle request failed for {symbol}: {exc}") from exc
        if ret != RET_OK:
            raise MoomooAdapterError(f"Moomoo candle request failed for {symbol}: {data}")
        return [row.to_dict() for _, row in data.iterrows()]

    def get_market_state(self, symbol: str) -> Mapping[str, Any]:
        ctx = self._context()
        try:
            from moomoo import RET_OK
            ret, data = ctx.get_market_state([symbol])
        except Exception as exc:
            raise MoomooAdapterError(f"Moomoo market-state request failed for {symbol}: {exc}") from exc
        if ret != RET_OK:
            raise MoomooAdapterError(f"Moomoo market-state request failed for {symbol}: {data}")
        return self._row(data)

    def close(self) -> None:
        if self._quote_ctx is not None:
            try:
                self._quote_ctx.close()
            finally:
                self._quote_ctx = None

    def __enter__(self) -> "MoomooOpenDTransport":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
