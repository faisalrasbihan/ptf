from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
import re

from app.core.config import Settings
from app.schemas.forecast import (
    ForecastPoint,
    HistoryPoint,
    ForecastRequest,
    ForecastResponse,
    ResolvedForecastRequest,
)
from app.services.calendar import next_continuous_timestamps, next_us_trading_timestamps
from app.services.errors import AppError, ErrorCode
from app.services.forecast_models import ForecastModelRegistry
from app.services.tiingo import TiingoProvider


ProgressReporter = Callable[[str, str, int], Awaitable[None]]


CRYPTO_HORIZONS = {
    "1h": ("1h", 1, timedelta(hours=1)),
    "4h": ("1h", 4, timedelta(hours=1)),
    "24h": ("1h", 24, timedelta(hours=1)),
    "7d": ("4h", 42, timedelta(hours=4)),
}
STOCK_HORIZON_PATTERN = re.compile(r"^([1-9]\d*)d$")


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
    model_spec = model_registry.resolve(payload.model)
    if payload.asset_type == "stock":
        match = STOCK_HORIZON_PATTERN.fullmatch(payload.horizon)
        if match is None:
            raise AppError(
                ErrorCode.BAD_REQUEST,
                "Stock horizon must use day format like '10d'.",
                400,
            )
        forecast_steps = int(match.group(1))
        if forecast_steps < settings.MIN_FORECAST_DAYS or forecast_steps > settings.MAX_FORECAST_DAYS:
            raise AppError(
                ErrorCode.BAD_REQUEST,
                f"stock horizon must be between {settings.MIN_FORECAST_DAYS}d and {settings.MAX_FORECAST_DAYS}d.",
                400,
            )
        ticker = payload.ticker
        bar_interval = "1d"
        tiingo_resample_freq = None
    else:
        if payload.horizon not in CRYPTO_HORIZONS:
            supported = ", ".join(CRYPTO_HORIZONS)
            raise AppError(
                ErrorCode.BAD_REQUEST,
                f"Unsupported crypto horizon '{payload.horizon}'. Supported horizons are: {supported}.",
                400,
            )
        bar_interval, forecast_steps, _ = CRYPTO_HORIZONS[payload.horizon]
        ticker = _normalize_crypto_ticker(payload.ticker)
        tiingo_resample_freq = "1hour" if bar_interval == "1h" else "4hour"

    return ResolvedForecastRequest(
        ticker=ticker,
        asset_type=payload.asset_type,
        model_alias=model_spec.alias,
        model_id=model_spec.model_id,
        horizon=payload.horizon,
        forecast_steps=forecast_steps,
        bar_interval=bar_interval,
        tiingo_resample_freq=tiingo_resample_freq,
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
        f"Using {resolved.model_alias} for {resolved.ticker} over horizon {resolved.horizon}.",
        12,
    )

    await _report_progress(progress, "fetching_history", "Fetching historical market data.", 20)
    history = await tiingo_provider.fetch_history(
        resolved.ticker,
        asset_type=resolved.asset_type,
        bar_interval=resolved.bar_interval,
    )
    await _report_progress(
        progress,
        "history_ready",
        f"Loaded {len(history)} historical price bars for {resolved.ticker}.",
        35,
    )

    await _report_progress(progress, "building_calendar", "Building forecast timestamps.", 42)
    forecast_timestamps = _forecast_timestamps(resolved, history[-1].timestamp)
    await _report_progress(
        progress,
        "calendar_ready",
        f"Prepared {len(forecast_timestamps)} future forecast timestamps.",
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
        forecast_timestamps,
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
            date=forecast_timestamps[index].date(),
            timestamp=forecast_timestamps[index],
            open=forecast_values.open[index],
            high=forecast_values.high[index],
            low=forecast_values.low[index],
            close=forecast_values.close[index],
            volume=forecast_values.volume[index],
            median=forecast_values.close[index],
        )
        for index in range(resolved.forecast_steps)
    ]

    return ForecastResponse(
        ticker=resolved.ticker,
        asset_type=resolved.asset_type,
        horizon=resolved.horizon,
        bar_interval=resolved.bar_interval,
        history=[
            HistoryPoint(
                date=point.date,
                timestamp=point.timestamp,
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
        generated_at=datetime.now(UTC),
    )


def _forecast_timestamps(resolved: ResolvedForecastRequest, last_history_timestamp: datetime) -> list[datetime]:
    if resolved.asset_type == "stock":
        return next_us_trading_timestamps(last_history_timestamp, resolved.forecast_steps)

    _, _, step = CRYPTO_HORIZONS[resolved.horizon]
    return next_continuous_timestamps(
        last_history_timestamp,
        steps=resolved.forecast_steps,
        step=step,
    )


def _normalize_crypto_ticker(ticker: str) -> str:
    compact = ticker.replace("/", "").replace("-", "").replace("_", "").strip().upper()
    if not compact.endswith("USD") or len(compact) <= 3:
        raise AppError(
            ErrorCode.BAD_REQUEST,
            "Crypto ticker must be a USD pair like BTCUSD, BTC/USD, or BTC-USD.",
            400,
        )
    return compact
