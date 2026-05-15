from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import numpy as np
import pandas as pd

from app.core.config import Settings
from app.services.errors import AppError, ErrorCode
from app.services.forecast_history import last_finite_volume, prepare_history
from app.services.kronos_forecaster import ForecastValues, KronosForecaster
from app.services.tiingo import KlinePoint


class ForecastAdapter(Protocol):
    async def predict(
        self,
        history: list[KlinePoint],
        forecast_dates: list[date],
        timeout_seconds: float,
    ) -> ForecastValues: ...


@dataclass(frozen=True, slots=True)
class ForecastModelSpec:
    alias: str
    display_name: str
    model_id: str


ModelFactory = Callable[[], ForecastAdapter]


class ForecastModelRegistry:
    def __init__(
        self,
        settings: Settings,
        *,
        specs: list[ForecastModelSpec] | None = None,
        factories: dict[str, ModelFactory] | None = None,
    ):
        self.settings = settings
        self._specs = specs if specs is not None else default_model_specs(settings)
        self._spec_by_alias = {spec.alias: spec for spec in self._specs}
        self._factories = factories if factories is not None else default_model_factories(settings)
        self._instances: dict[str, ForecastAdapter] = {}
        self._locks = {alias: asyncio.Lock() for alias in self._spec_by_alias}

    @property
    def specs(self) -> list[ForecastModelSpec]:
        return list(self._specs)

    def resolve(self, alias: str | None) -> ForecastModelSpec:
        model_alias = alias or self.settings.KRONOS_MODEL_ALIAS
        spec = self._spec_by_alias.get(model_alias)
        if spec is None:
            supported = ", ".join(self._spec_by_alias)
            raise AppError(
                ErrorCode.BAD_REQUEST,
                f"Unsupported model '{model_alias}'. Supported models are: {supported}.",
                400,
            )
        return spec

    async def get(self, alias: str) -> ForecastAdapter:
        self.resolve(alias)
        if alias in self._instances:
            return self._instances[alias]

        async with self._locks[alias]:
            if alias not in self._instances:
                self._instances[alias] = await asyncio.to_thread(self._factories[alias])
            return self._instances[alias]

    async def predict(
        self,
        model_alias: str,
        history: list[KlinePoint],
        forecast_dates: list[date],
        timeout_seconds: float,
    ) -> ForecastValues:
        adapter = await self.get(model_alias)
        return await adapter.predict(history, forecast_dates, timeout_seconds)


class Chronos2Forecaster:
    QUANTILE_LEVELS = [0.1, 0.5, 0.9]

    def __init__(self, pipeline: object, settings: Settings):
        self.pipeline = pipeline
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings) -> "Chronos2Forecaster":
        from chronos import Chronos2Pipeline

        pipeline = Chronos2Pipeline.from_pretrained(
            settings.CHRONOS_MODEL_ID,
            device_map=settings.CHRONOS_DEVICE_MAP,
        )
        return cls(pipeline, settings)

    async def predict(
        self,
        history: list[KlinePoint],
        forecast_dates: list[date],
        timeout_seconds: float,
    ) -> ForecastValues:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._predict_sync, history, forecast_dates),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise AppError(ErrorCode.MODEL_TIMEOUT, "Forecast model timed out.", 504) from exc
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                ErrorCode.MODEL_TIMEOUT,
                "Forecast model failed to generate a forecast.",
                504,
            ) from exc

    def _predict_sync(self, history: list[KlinePoint], forecast_dates: list[date]) -> ForecastValues:
        context = prepare_history(history, require_ohlcv=False, min_points=3)
        volume = last_finite_volume(context)
        context_df = pd.DataFrame(
            {
                "item_id": ["ticker"] * len(context),
                "timestamp": pd.date_range("2000-01-01", periods=len(context), freq="D"),
                "target": [point.close for point in context],
            }
        )
        pred_df = self.pipeline.predict_df(
            context_df,
            prediction_length=len(forecast_dates),
            quantile_levels=self.QUANTILE_LEVELS,
            id_column="item_id",
            timestamp_column="timestamp",
            target="target",
            validate_inputs=False,
        )
        pred_df = pred_df.head(len(forecast_dates))
        median = _float_column(pred_df, "0.5", "predictions")
        low = _float_column(pred_df, "0.1", "predictions")
        high = _float_column(pred_df, "0.9", "predictions")
        return _close_band_values(median, low, high, volume)


class TimesFMForecaster:
    def __init__(self, model: object, settings: Settings):
        self.model = model
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings) -> "TimesFMForecaster":
        import timesfm

        model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(settings.TIMESFM_MODEL_ID)
        model.compile(
            timesfm.ForecastConfig(
                max_context=settings.TIMESFM_MAX_CONTEXT,
                max_horizon=settings.TIMESFM_MAX_HORIZON,
                normalize_inputs=True,
                use_continuous_quantile_head=True,
                force_flip_invariance=True,
                infer_is_positive=True,
                fix_quantile_crossing=True,
            )
        )
        return cls(model, settings)

    async def predict(
        self,
        history: list[KlinePoint],
        forecast_dates: list[date],
        timeout_seconds: float,
    ) -> ForecastValues:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._predict_sync, history, forecast_dates),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise AppError(ErrorCode.MODEL_TIMEOUT, "Forecast model timed out.", 504) from exc
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                ErrorCode.MODEL_TIMEOUT,
                "Forecast model failed to generate a forecast.",
                504,
            ) from exc

    def _predict_sync(self, history: list[KlinePoint], forecast_dates: list[date]) -> ForecastValues:
        context = prepare_history(history, require_ohlcv=False, min_points=3)[-self.settings.TIMESFM_MAX_CONTEXT :]
        volume = last_finite_volume(context)
        point_forecast, quantile_forecast = self.model.forecast(
            horizon=len(forecast_dates),
            inputs=[np.array([point.close for point in context], dtype=float)],
        )
        median = [float(value) for value in np.asarray(point_forecast)[0, : len(forecast_dates)]]
        low, high = _timesfm_bounds(quantile_forecast, median)
        return _close_band_values(median, low, high, volume)


def default_model_specs(settings: Settings) -> list[ForecastModelSpec]:
    return [
        ForecastModelSpec(settings.KRONOS_MODEL_ALIAS, "Kronos Base", settings.KRONOS_MODEL_ID),
        ForecastModelSpec(settings.CHRONOS_MODEL_ALIAS, "Amazon Chronos-2", settings.CHRONOS_MODEL_ID),
        ForecastModelSpec(settings.TIMESFM_MODEL_ALIAS, "Google TimesFM 2.5", settings.TIMESFM_MODEL_ID),
    ]


def default_model_factories(settings: Settings) -> dict[str, ModelFactory]:
    return {
        settings.KRONOS_MODEL_ALIAS: lambda: KronosForecaster.from_settings(settings),
        settings.CHRONOS_MODEL_ALIAS: lambda: Chronos2Forecaster.from_settings(settings),
        settings.TIMESFM_MODEL_ALIAS: lambda: TimesFMForecaster.from_settings(settings),
    }


def _float_column(df: pd.DataFrame, primary: str, fallback: str) -> list[float]:
    column = primary if primary in df else fallback
    return [float(value) for value in df[column].to_list()]


def _close_band_values(
    median: list[float],
    low: list[float],
    high: list[float],
    volume: float,
) -> ForecastValues:
    lows: list[float] = []
    highs: list[float] = []
    for index, close in enumerate(median):
        low_value = low[index] if index < len(low) else close
        high_value = high[index] if index < len(high) else close
        lows.append(min(low_value, close, high_value))
        highs.append(max(low_value, close, high_value))
    return ForecastValues(
        open=list(median),
        high=highs,
        low=lows,
        close=list(median),
        volume=[volume for _ in median],
    )


def _timesfm_bounds(quantile_forecast: object, median: list[float]) -> tuple[list[float], list[float]]:
    if quantile_forecast is None:
        return median, median
    quantiles = np.asarray(quantile_forecast)
    if quantiles.ndim != 3 or quantiles.shape[0] == 0:
        return median, median
    horizon = len(median)
    if quantiles.shape[2] >= 10:
        return (
            [float(value) for value in quantiles[0, :horizon, 1]],
            [float(value) for value in quantiles[0, :horizon, 9]],
        )
    if quantiles.shape[2] >= 2:
        return (
            [float(value) for value in quantiles[0, :horizon, 0]],
            [float(value) for value in quantiles[0, :horizon, -1]],
        )
    return median, median
