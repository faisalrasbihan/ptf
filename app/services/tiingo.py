from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from app.core.config import Settings
from app.services.errors import AppError, ErrorCode


@dataclass(slots=True)
class KlinePoint:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class TiingoProvider:
    BASE_URL = "https://api.tiingo.com/tiingo/daily"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def fetch_history(self, ticker: str) -> list[KlinePoint]:
        if not self.settings.TIINGO_KEY:
            raise AppError(
                ErrorCode.DATA_SOURCE_ERROR,
                "Tiingo API key is not configured.",
                502,
            )

        end_date = date.today()
        start_date = end_date - timedelta(days=365 * self.settings.HISTORY_YEARS)
        url = f"{self.BASE_URL}/{ticker.lower()}/prices"
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

        history = self._parse_history(payload)
        if not history:
            raise AppError(
                ErrorCode.TICKER_NOT_FOUND,
                f"No data found for ticker '{ticker}'.",
                404,
            )

        return history

    def _parse_history(self, payload: Any) -> list[KlinePoint]:
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
                parsed_date = _parse_tiingo_date(str(raw_date))
                open_price = float(open_value)
                high = float(high_value)
                low = float(low_value)
                close = float(close_value)
                volume = float(volume_value or 0.0)
            except (TypeError, ValueError):
                continue

            history.append(
                KlinePoint(
                    date=parsed_date,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
            )

        history.sort(key=lambda point: point.date)
        return history


def _parse_tiingo_date(value: str) -> date:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).date()


def _prefer_adjusted(item: dict[str, Any], field: str) -> Any:
    adjusted_key = f"adj{field[:1].upper()}{field[1:]}"
    value = item.get(adjusted_key)
    if value is not None:
        return value
    return item.get(field)
