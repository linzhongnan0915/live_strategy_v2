"""
OpenBB market data adapter (prototype).

What: Fetch quotes and historical closes via OpenBB providers (default yfinance).
Why: Prototype price ingestion layer; rule_engine still uses sample/computed paths unless pointed elsewhere.
Inputs: Ticker symbols, date range, provider name.
Outputs: Normalized long-format price history (date, ticker, close, source).
Pitfalls: VIX requires ^VIX mapping on yfinance; not Bloomberg-quality live data.
"""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

OPENBB_IMPORT_ERROR = "OpenBB is not installed. Install with: pip install openbb"

PRICE_HISTORY_COLUMNS = ["date", "ticker", "close", "source"]

YFINANCE_VIX_PROXY = "^VIX"

VIX_MAPPING_NOTE = (
    "VIX is requested as ticker VIX but fetched via ^VIX on yfinance; "
    "output rows use ticker VIX."
)


def _import_openbb() -> Any:
    """Lazy import so unit tests run without OpenBB installed."""
    try:
        from openbb import obb  # type: ignore import-not-found
    except ImportError as exc:
        raise ImportError(OPENBB_IMPORT_ERROR) from exc
    return obb


def _source_label(provider: str) -> str:
    return f"openbb_{provider.strip().lower()}"


def _map_symbol_for_provider(symbol: str, provider: str) -> str:
    """Map internal ticker to provider-specific symbol when needed."""
    sym = str(symbol).strip().upper()
    if sym == "VIX" and provider.strip().lower() == "yfinance":
        return YFINANCE_VIX_PROXY
    return sym


def _normalize_historical_frame(
    raw: pd.DataFrame,
    ticker: str,
    source: str,
) -> pd.DataFrame:
    """Normalize a single-symbol OpenBB historical DataFrame to long format."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=PRICE_HISTORY_COLUMNS)

    frame = raw.copy()
    if "date" not in frame.columns and "datetime" not in frame.columns:
        frame = frame.reset_index()
    if frame.columns.dtype == object:
        frame.columns = [str(col).lower() for col in frame.columns]

    date_col = None
    for candidate in ("date", "datetime", "index"):
        if candidate in frame.columns:
            date_col = candidate
            break
    if date_col is None:
        raise ValueError(f"OpenBB historical output missing date column: {list(frame.columns)}")

    close_col = None
    for candidate in ("close", "adj close", "adj_close", "adjclose"):
        if candidate in frame.columns:
            close_col = candidate
            break
    if close_col is None:
        raise ValueError(f"OpenBB historical output missing close column: {list(frame.columns)}")

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(frame[date_col], errors="coerce"),
            "ticker": str(ticker).strip().upper(),
            "close": pd.to_numeric(frame[close_col], errors="coerce"),
            "source": source,
        }
    )
    out = out.dropna(subset=["date", "close"]).copy()
    out["date"] = out["date"].dt.normalize()
    return out[PRICE_HISTORY_COLUMNS]


def validate_price_history_output(
    df: pd.DataFrame,
    *,
    allow_empty: bool = False,
) -> None:
    """
    Validate normalized long-format price history.

    Raises ValueError on schema, null close, or duplicate ticker/date rows.
    """
    if df.empty:
        if allow_empty:
            return
        raise ValueError("price history is empty")
    if list(df.columns) != PRICE_HISTORY_COLUMNS:
        raise ValueError(
            f"price history columns must be {PRICE_HISTORY_COLUMNS}; got {list(df.columns)}"
        )
    if df["close"].isna().any():
        raise ValueError("price history contains missing close values")
    if not pd.api.types.is_numeric_dtype(df["close"]):
        raise ValueError("price history close must be numeric")
    if df["date"].isna().any():
        raise ValueError("price history date must be parseable")

    dupes = df.duplicated(subset=["date", "ticker"], keep=False)
    if dupes.any():
        bad = df.loc[dupes, ["date", "ticker"]].head(5)
        raise ValueError(f"duplicate ticker/date rows in price history: {bad.to_dict('records')}")


def fetch_openbb_quote(
    symbol: str,
    provider: str = "yfinance",
) -> dict[str, Any]:
    """
    Fetch a latest quote snapshot for one symbol via OpenBB.

    Returns dict with symbol, close, date, provider, source.
    """
    obb = _import_openbb()
    ticker = str(symbol).strip().upper()
    fetch_symbol = _map_symbol_for_provider(ticker, provider)
    source = _source_label(provider)

    quote_fn = getattr(getattr(getattr(obb, "equity", None), "price", None), "quote", None)
    if callable(quote_fn):
        try:
            raw = quote_fn(symbol=fetch_symbol, provider=provider).to_df()
            if raw is not None and not raw.empty:
                frame = raw.copy()
                frame.columns = [str(c).lower() for c in frame.columns]
                close_val = None
                for col in ("last", "close", "price"):
                    if col in frame.columns:
                        close_val = float(frame[col].iloc[0])
                        break
                if close_val is not None:
                    as_of = pd.Timestamp.utcnow().date().isoformat()
                    if "date" in frame.columns:
                        as_of = str(pd.to_datetime(frame["date"].iloc[0]).date())
                    return {
                        "symbol": ticker,
                        "close": close_val,
                        "date": as_of,
                        "provider": provider,
                        "source": source,
                        "fetch_symbol": fetch_symbol,
                    }
        except Exception:
            pass

    hist = obb.equity.price.historical(
        symbol=fetch_symbol,
        provider=provider,
    ).to_df()
    normalized = _normalize_historical_frame(hist, ticker, source)
    if normalized.empty:
        raise ValueError(f"No quote/history data returned for symbol {ticker}")
    last = normalized.sort_values("date").iloc[-1]
    return {
        "symbol": ticker,
        "close": float(last["close"]),
        "date": str(pd.Timestamp(last["date"]).date()),
        "provider": provider,
        "source": source,
        "fetch_symbol": fetch_symbol,
    }


def fetch_openbb_price_history(
    symbols: list[str],
    start_date: str,
    end_date: str,
    provider: str = "yfinance",
) -> pd.DataFrame:
    """
    Fetch historical daily closes for symbols via OpenBB.

    Returns long-format DataFrame: date, ticker, close, source.
    Symbols with no rows are omitted; check script output missing_tickers for coverage.
    """
    if not symbols:
        return pd.DataFrame(columns=PRICE_HISTORY_COLUMNS)

    obb = _import_openbb()
    source = _source_label(provider)
    requested = [str(s).strip().upper() for s in symbols]

    if "VIX" in requested and provider.strip().lower() == "yfinance":
        warnings.warn(VIX_MAPPING_NOTE, stacklevel=2)

    frames: list[pd.DataFrame] = []
    for ticker in requested:
        fetch_symbol = _map_symbol_for_provider(ticker, provider)
        try:
            result = obb.equity.price.historical(
                symbol=fetch_symbol,
                start_date=start_date,
                end_date=end_date,
                provider=provider,
            )
            raw = result.to_df()
            chunk = _normalize_historical_frame(raw, ticker, source)
            if not chunk.empty:
                frames.append(chunk)
        except Exception:
            continue

    if not frames:
        return pd.DataFrame(columns=PRICE_HISTORY_COLUMNS)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["date", "ticker"]).reset_index(drop=True)
    validate_price_history_output(combined)
    return combined[PRICE_HISTORY_COLUMNS]
