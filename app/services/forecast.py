from datetime import UTC, datetime

from app.core.config import Settings
from app.schemas.forecast import (
    ForecastPoint,
    HistoryPoint,
    ForecastRequest,
    ForecastResponse,
    ResolvedForecastRequest,
)
from app.services.calendar import get_calendar_name, next_trading_dates
from app.services.errors import AppError, ErrorCode
from app.services.kronos_forecaster import KronosForecaster
from app.services.tiingo import TiingoProvider


def resolve_request(payload: ForecastRequest, settings: Settings) -> ResolvedForecastRequest:
    get_calendar_name(payload.exchange)

    days = payload.days if payload.days is not None else settings.DEFAULT_FORECAST_DAYS
    if days < settings.MIN_FORECAST_DAYS or days > settings.MAX_FORECAST_DAYS:
        raise AppError(
            ErrorCode.BAD_REQUEST,
            f"days must be between {settings.MIN_FORECAST_DAYS} and {settings.MAX_FORECAST_DAYS}.",
            400,
        )

    model_alias = payload.model or settings.KRONOS_MODEL_ALIAS
    if model_alias != settings.KRONOS_MODEL_ALIAS:
        raise AppError(
            ErrorCode.BAD_REQUEST,
            f"Unsupported model '{model_alias}'. Supported model is {settings.KRONOS_MODEL_ALIAS}.",
            400,
        )

    return ResolvedForecastRequest(
        ticker=payload.ticker,
        exchange=payload.exchange,
        model_alias=model_alias,
        model_id=settings.KRONOS_MODEL_ID,
        days=days,
    )


async def build_forecast_response(
    payload: ForecastRequest,
    settings: Settings,
    tiingo_provider: TiingoProvider,
    forecaster: KronosForecaster,
) -> ForecastResponse:
    resolved = resolve_request(payload, settings)
    history = await tiingo_provider.fetch_history(resolved.ticker, resolved.exchange)
    forecast_dates = next_trading_dates(
        resolved.exchange,
        history[-1].date,
        resolved.days,
    )

    forecast_values = await forecaster.predict(
        history,
        forecast_dates,
        settings.MODEL_TIMEOUT_SECONDS,
    )

    forecast = [
        ForecastPoint(
            date=forecast_dates[index],
            open=forecast_values.open[index],
            high=forecast_values.high[index],
            low=forecast_values.low[index],
            close=forecast_values.close[index],
            volume=forecast_values.volume[index],
            median=forecast_values.close[index],
        )
        for index in range(resolved.days)
    ]

    return ForecastResponse(
        ticker=resolved.ticker,
        exchange=resolved.exchange,
        history=[
            HistoryPoint(
                date=point.date,
                open=point.open,
                high=point.high,
                low=point.low,
                close=point.close,
                volume=point.volume,
            )
            for point in history
        ],
        forecast=forecast,
        model=resolved.model_alias,
        days=resolved.days,
        generated_at=datetime.now(UTC),
    )
