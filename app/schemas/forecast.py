from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ForecastRequest(BaseModel):
    ticker: str = Field(min_length=1)
    model: str | None = None
    days: int | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        ticker = value.strip().upper()
        if not ticker:
            raise ValueError("Ticker is required.")
        return ticker

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
    model_alias: str
    model_id: str
    days: int
