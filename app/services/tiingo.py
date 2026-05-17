import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.core.config import Settings
from app.services.errors import AppError, ErrorCode
from app.services.tiingo_cache import TiingoHistoryCache


@dataclass(slots=True)
class KlinePoint:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def date(self) -> date:
        return self.timestamp.date()


class TiingoProvider:
    STOCK_BASE_URL = "https://api.tiingo.com/tiingo/daily"
    CRYPTO_BASE_URL = "https://api.tiingo.com/tiingo/crypto/prices"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def fetch_history(
        self,
        ticker: str,
        *,
        asset_type: str = "stock",
        bar_interval: str = "1d",
    ) -> list[KlinePoint]:
        if not self.settings.TIINGO_KEY:
            raise AppError(
                ErrorCode.DATA_SOURCE_ERROR,
                "Tiingo API key is not configured.",
                502,
            )

        ticker_key = ticker.strip().upper()
        end_date = date.today()
        start_date = end_date - timedelta(days=365 * self.settings.HISTORY_YEARS)
        cache = TiingoHistoryCache(self.settings)

        if cache.enabled:
            cached_history = await cache.get_history(
                ticker_key,
                start_date,
                end_date,
                KlinePoint,
                asset_type=asset_type,
                bar_interval=bar_interval,
            )
            if cached_history is not None:
                return cached_history

            lock_token = await cache.acquire_lock(
                ticker_key,
                start_date,
                end_date,
                asset_type=asset_type,
                bar_interval=bar_interval,
            )
            if lock_token is not None:
                try:
                    history = await self._fetch_history_from_tiingo(
                        ticker_key,
                        start_date,
                        end_date,
                        asset_type=asset_type,
                        bar_interval=bar_interval,
                    )
                    await cache.set_history(
                        ticker_key,
                        start_date,
                        end_date,
                        history,
                        asset_type=asset_type,
                        bar_interval=bar_interval,
                    )
                    return history
                finally:
                    await cache.release_lock(
                        ticker_key,
                        start_date,
                        end_date,
                        lock_token,
                        asset_type=asset_type,
                        bar_interval=bar_interval,
                    )

            cached_history = await self._wait_for_cached_history(
                cache,
                ticker_key,
                start_date,
                end_date,
                asset_type=asset_type,
                bar_interval=bar_interval,
            )
            if cached_history is not None:
                return cached_history

        history = await self._fetch_history_from_tiingo(
            ticker_key,
            start_date,
            end_date,
            asset_type=asset_type,
            bar_interval=bar_interval,
        )
        if cache.enabled:
            await cache.set_history(
                ticker_key,
                start_date,
                end_date,
                history,
                asset_type=asset_type,
                bar_interval=bar_interval,
            )
        return history

    async def _wait_for_cached_history(
        self,
        cache: TiingoHistoryCache,
        ticker: str,
        start_date: date,
        end_date: date,
        *,
        asset_type: str,
        bar_interval: str,
    ) -> list[KlinePoint] | None:
        for _ in range(5):
            await asyncio.sleep(0.1)
            cached_history = await cache.get_history(
                ticker,
                start_date,
                end_date,
                KlinePoint,
                asset_type=asset_type,
                bar_interval=bar_interval,
            )
            if cached_history is not None:
                return cached_history
        return None

    async def _fetch_history_from_tiingo(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        *,
        asset_type: str,
        bar_interval: str,
    ) -> list[KlinePoint]:
        if asset_type == "crypto":
            url = self.CRYPTO_BASE_URL
            params = {
                "tickers": ticker.lower(),
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "resampleFreq": _crypto_resample_freq(bar_interval),
                "token": self.settings.TIINGO_KEY,
            }
        else:
            url = f"{self.STOCK_BASE_URL}/{ticker.lower()}/prices"
            params = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "token": self.settings.TIINGO_KEY,
            }

        try:
            async with httpx.AsyncClient(timeout=self.settings.TIINGO_TIMEOUT_SECONDS) as client:
                response = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise AppError(
                ErrorCode.DATA_SOURCE_ERROR,
                "Unable to fetch price history from Tiingo.",
                502,
            ) from exc

        if response.status_code == 404:
            raise AppError(
                ErrorCode.TICKER_NOT_FOUND,
                f"No data found for ticker '{ticker}'.",
                404,
            )
        if response.status_code == 429:
            raise AppError(
                ErrorCode.RATE_LIMITED,
                "Tiingo rate limit exceeded. Please try again later.",
                429,
            )
        if response.status_code >= 400:
            raise AppError(
                ErrorCode.DATA_SOURCE_ERROR,
                "Tiingo returned an unexpected error.",
                502,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise AppError(
                ErrorCode.DATA_SOURCE_ERROR,
                "Tiingo returned malformed JSON.",
                502,
            ) from exc

        history = self._parse_crypto_history(payload) if asset_type == "crypto" else self._parse_stock_history(payload)
        if not history:
            raise AppError(
                ErrorCode.TICKER_NOT_FOUND,
                f"No data found for ticker '{ticker}'.",
                404,
            )

        return history

    def _parse_stock_history(self, payload: Any) -> list[KlinePoint]:
        if not isinstance(payload, list):
            raise AppError(
                ErrorCode.DATA_SOURCE_ERROR,
                "Tiingo returned an unexpected response shape.",
                502,
            )

        history: list[KlinePoint] = []
        for item in payload:
            if not isinstance(item, dict):
                continue

            raw_date = item.get("date")
            open_value = _prefer_adjusted(item, "open")
            high_value = _prefer_adjusted(item, "high")
            low_value = _prefer_adjusted(item, "low")
            close_value = _prefer_adjusted(item, "close")
            volume_value = _prefer_adjusted(item, "volume")
            if raw_date is None or None in {open_value, high_value, low_value, close_value}:
                continue

            try:
                timestamp = _parse_tiingo_timestamp(str(raw_date))
                open_price = float(open_value)
                high = float(high_value)
                low = float(low_value)
                close = float(close_value)
                volume = float(volume_value or 0.0)
            except (TypeError, ValueError):
                continue

            history.append(
                KlinePoint(
                    timestamp=timestamp,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
            )

        history.sort(key=lambda point: point.timestamp)
        return history

    def _parse_crypto_history(self, payload: Any) -> list[KlinePoint]:
        if not isinstance(payload, list):
            raise AppError(
                ErrorCode.DATA_SOURCE_ERROR,
                "Tiingo returned an unexpected response shape.",
                502,
            )

        history: list[KlinePoint] = []
        for item in payload:
            if not isinstance(item, dict):
                continue

            price_data = item.get("priceData")
            if isinstance(price_data, dict):
                bars = [price_data]
            elif isinstance(price_data, list):
                bars = price_data
            else:
                continue

            for bar in bars:
                if not isinstance(bar, dict):
                    continue

                raw_date = bar.get("date")
                open_value = bar.get("open")
                high_value = bar.get("high")
                low_value = bar.get("low")
                close_value = bar.get("close")
                volume_value = bar.get("volume")
                if raw_date is None or None in {open_value, high_value, low_value, close_value}:
                    continue

                try:
                    timestamp = _parse_tiingo_timestamp(str(raw_date))
                    open_price = float(open_value)
                    high = float(high_value)
                    low = float(low_value)
                    close = float(close_value)
                    volume = float(volume_value or 0.0)
                except (TypeError, ValueError):
                    continue

                history.append(
                    KlinePoint(
                        timestamp=timestamp,
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                    )
                )

        history.sort(key=lambda point: point.timestamp)
        return history


def _parse_tiingo_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    timestamp = datetime.fromisoformat(normalized)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _prefer_adjusted(item: dict[str, Any], field: str) -> Any:
    adjusted_key = f"adj{field[:1].upper()}{field[1:]}"
    value = item.get(adjusted_key)
    if value is not None:
        return value
    return item.get(field)


def _crypto_resample_freq(bar_interval: str) -> str:
    if bar_interval == "1h":
        return "1hour"
    if bar_interval == "4h":
        return "4hour"
    raise AppError(
        ErrorCode.BAD_REQUEST,
        f"Unsupported crypto bar interval '{bar_interval}'.",
        400,
    )
