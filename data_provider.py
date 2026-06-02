from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd
import yfinance as yf


FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
PRICE_DEVIATION_LIMIT = 0.30


def _get_finnhub_api_key() -> str:
    api_key = os.getenv("FINNHUB_API_KEY", "").strip()
    if api_key:
        return api_key

    try:
        import streamlit as st

        return str(st.secrets.get("FINNHUB_API_KEY", "")).strip()
    except Exception:
        return ""


def _to_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    return int(number) if number is not None else None


def _get_data_status(price: float | None, previous_close: float | None) -> str:
    if price is None or price == 0:
        return "异常"
    if previous_close and abs(price - previous_close) / previous_close > PRICE_DEVIATION_LIMIT:
        return "异常"
    return "正常"


def _change_percent(price: float | None, previous_close: float | None) -> float | None:
    if price is None or not previous_close:
        return None
    return (price - previous_close) / previous_close * 100


def _get_finnhub_quote(ticker: str, api_key: str) -> dict[str, Any]:
    query = urlencode({"symbol": ticker, "token": api_key})
    with urlopen(f"{FINNHUB_QUOTE_URL}?{query}", timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict) or "c" not in payload:
        raise ValueError("Finnhub 返回格式异常")

    price = _to_float(payload.get("c"))
    previous_close = _to_float(payload.get("pc"))
    return {
        "ticker": ticker,
        "price": price,
        "previous_close": previous_close,
        "change_percent": _change_percent(price, previous_close),
        "volume": None,
        "source": "Finnhub",
        "data_status": _get_data_status(price, previous_close),
    }


def _get_yfinance_quote(ticker: str) -> dict[str, Any]:
    stock = yf.Ticker(ticker)
    history = stock.history(period="5d", interval="1d", auto_adjust=False)
    if history.empty or "Close" not in history:
        raise ValueError("yfinance 未获取到行情")

    closes = history["Close"].dropna()
    if len(closes) < 2:
        raise ValueError("yfinance 行情不足")

    price = _to_float(closes.iloc[-1])
    previous_close = _to_float(closes.iloc[-2])
    volumes = history["Volume"].dropna() if "Volume" in history else pd.Series(dtype=float)
    volume = _to_int(volumes.iloc[-1]) if not volumes.empty else None

    try:
        fast_info = stock.fast_info
        price = _to_float(fast_info.get("last_price")) or price
        previous_close = _to_float(fast_info.get("previous_close")) or previous_close
        volume = _to_int(fast_info.get("last_volume")) or volume
    except Exception:
        pass

    return {
        "ticker": ticker,
        "price": price,
        "previous_close": previous_close,
        "change_percent": _change_percent(price, previous_close),
        "volume": volume,
        "source": "yfinance",
        "data_status": _get_data_status(price, previous_close),
    }


def get_quote(ticker: str) -> dict[str, Any]:
    """Return a normalized quote, preferring Finnhub and falling back to yfinance."""
    normalized_ticker = ticker.strip().upper()
    api_key = _get_finnhub_api_key()
    if api_key:
        try:
            return _get_finnhub_quote(normalized_ticker, api_key)
        except Exception:
            pass
    return _get_yfinance_quote(normalized_ticker)


def get_history(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """Return historical prices for technical indicators.

    Finnhub quote responses do not include daily history in the free quote
    endpoint, so the MVP keeps yfinance as the historical-series backend.
    """
    history = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
    if history.empty or "Close" not in history:
        raise ValueError("未获取到历史行情")
    return history
