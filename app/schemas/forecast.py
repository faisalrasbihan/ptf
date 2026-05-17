from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    asset_type: Literal["stock", "crypto"]
    model: str | None = None
    horizon: str = Field(min_length=1)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        ticker = value.strip().upper()
        if not ticker:
            raise ValueError("Ticker is required.")
        return ticker

    @field_validator("asset_type", mode="before")
    @classmethod
    def normalize_asset_type(cls, value: Any) -> str:
        return str(value).strip().lower()

    @field_validator("model", mode="before")
    @classmethod
    def normalize_empty_model(cls, value: Any) -> str | None:
        if value is None or value == "":
            return None
        return str(value)

    @field_validator("horizon", mode="before")
    @classmethod
    def normalize_horizon(cls, value: Any) -> str:
        horizon = str(value).strip().lower()
        if not horizon:
            raise ValueError("Horizon is required.")
        return horizon


class HistoryPoint(BaseModel):
    date: date
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class ForecastPoint(BaseModel):
    date: date
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    median: float


class ForecastResponse(BaseModel):
    ticker: str
    asset_type: Literal["stock", "crypto"]
    horizon: str
    bar_interval: str
    history: list[HistoryPoint]
    forecast: list[ForecastPoint]
    model: str
    generated_at: datetime


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ResolvedForecastRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    ticker: str
    asset_type: Literal["stock", "crypto"]
    model_alias: str
    model_id: str
    horizon: str
    forecast_steps: int
    bar_interval: str
    tiingo_resample_freq: str | None = None
