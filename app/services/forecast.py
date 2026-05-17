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
from app.services.forecast_models import ForecastModelRegistry
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


def resolve_request(
    payload: ForecastRequest,
    settings: Settings,
    model_registry: ForecastModelRegistry,
) -> ResolvedForecastRequest:
    days = payload.days if payload.days is not None else settings.DEFAULT_FORECAST_DAYS
    if days < settings.MIN_FORECAST_DAYS or days > settings.MAX_FORECAST_DAYS:
        raise AppError(
            ErrorCode.BAD_REQUEST,
            f"days must be between {settings.MIN_FORECAST_DAYS} and {settings.MAX_FORECAST_DAYS}.",
            400,
        )

    model_spec = model_registry.resolve(payload.model)

    return ResolvedForecastRequest(
        ticker=payload.ticker,
        model_alias=model_spec.alias,
        model_id=model_spec.model_id,
        days=days,
    )


async def build_forecast_response(
    payload: ForecastRequest,
    settings: Settings,
    tiingo_provider: TiingoProvider,
    model_registry: ForecastModelRegistry,
    progress: ProgressReporter | None = None,
) -> ForecastResponse:
    await _report_progress(progress, "validating_request", "Validating forecast request.", 5)
    resolved = resolve_request(payload, settings, model_registry)
    await _report_progress(
        progress,
        "model_selected",
        f"Using {resolved.model_alias} for {resolved.ticker} over {resolved.days} trading days.",
        12,
    )

    await _report_progress(progress, "fetching_history", "Fetching historical market data.", 20)
    history = await tiingo_provider.fetch_history(resolved.ticker)
    await _report_progress(
        progress,
        "history_ready",
        f"Loaded {len(history)} historical price bars for {resolved.ticker}.",
        35,
    )

    await _report_progress(progress, "building_calendar", "Building forecast trading calendar.", 42)
    forecast_dates = next_us_trading_dates(
        history[-1].date,
        resolved.days,
    )
    await _report_progress(
        progress,
        "calendar_ready",
        f"Prepared {len(forecast_dates)} future trading dates.",
        50,
    )

    await _report_progress(
        progress,
        "preparing_model_input",
        f"Preparing historical market context for {resolved.model_alias}.",
        58,
    )
    await _report_progress(progress, "running_model", f"Running {resolved.model_alias} forecast model.", 65)
    forecast_values = await model_registry.predict(
        resolved.model_alias,
        history,
        forecast_dates,
        settings.MODEL_TIMEOUT_SECONDS,
    )
    await _report_progress(
        progress,
        "model_complete",
        f"{resolved.model_alias} returned {len(forecast_values.close)} forecast points.",
        82,
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
