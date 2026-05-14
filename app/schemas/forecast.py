from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ForecastRequest(BaseModel):
    ticker: str = Field(min_length=1)
    exchange: str = "XNAS"
    model: str | None = None
    days: int | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        ticker = value.strip().upper()
        if not ticker:
            raise ValueError("Ticker is required.")
        return ticker

    @field_validator("exchange", mode="before")
    @classmethod
    def default_exchange(cls, value: Any) -> str:
        if value is None or value == "":
            return "XNAS"
        return str(value)

    @field_validator("exchange")
    @classmethod
    def normalize_exchange(cls, value: str) -> str:
        exchange = value.strip().upper()
        if not exchange:
            raise ValueError("Exchange is required.")
        return exchange

    @field_validator("model", mode="before")
    @classmethod
    def normalize_empty_model(cls, value: Any) -> str | None:
        if value is None or value == "":
            return None
        return str(value)

    @field_validator("days", mode="before")
    @classmethod
    def normalize_empty_days(cls, value: Any) -> int | None:
        if value is None or value == "":
            return None
        return value


class HistoryPoint(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class ForecastPoint(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    median: float


class ForecastResponse(BaseModel):
    ticker: str
    exchange: str
    history: list[HistoryPoint]
    forecast: list[ForecastPoint]
    model: str
    days: int
    generated_at: datetime


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ResolvedForecastRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    ticker: str
    exchange: str
    model_alias: str
    model_id: str
    days: int
