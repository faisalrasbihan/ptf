from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.core.config import Settings
from app.schemas.forecast import (
    ForecastPoint,
    HistoryPoint,
    ForecastRequest,
    ForecastResponse,
    ResolvedForecastRequest,
)
from app.services.calendar import next_us_trading_dates
from app.services.errors import AppError, ErrorCode
from app.services.kronos_forecaster import KronosForecaster
from app.services.tiingo import TiingoProvider


ProgressReporter = Callable[[str, str, int], Awaitable[None]]


async def _report_progress(
    progress: ProgressReporter | None,
    phase: str,
    message: str,
    percent: int,
) -> None:
    if progress is not None:
        await progress(phase, message, percent)


def resolve_request(payload: ForecastRequest, settings: Settings) -> ResolvedForecastRequest:
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
        model_alias=model_alias,
        model_id=settings.KRONOS_MODEL_ID,
        days=days,
    )


async def build_forecast_response(
    payload: ForecastRequest,
    settings: Settings,
    tiingo_provider: TiingoProvider,
    forecaster: KronosForecaster,
    progress: ProgressReporter | None = None,
) -> ForecastResponse:
    await _report_progress(progress, "validating_request", "Validating forecast request.", 5)
    resolved = resolve_request(payload, settings)

    await _report_progress(progress, "fetching_history", "Fetching historical market data.", 20)
    history = await tiingo_provider.fetch_history(resolved.ticker)

    await _report_progress(progress, "building_calendar", "Building forecast trading calendar.", 35)
    forecast_dates = next_us_trading_dates(
        history[-1].date,
        resolved.days,
    )

    await _report_progress(progress, "running_model", "Running Kronos forecast model.", 55)
    forecast_values = await forecaster.predict(
        history,
        forecast_dates,
        settings.MODEL_TIMEOUT_SECONDS,
    )

    await _report_progress(progress, "formatting_response", "Formatting forecast response.", 90)
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
