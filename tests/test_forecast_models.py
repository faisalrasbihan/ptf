import asyncio
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.services.errors import AppError
from app.services.forecast_models import (
    Chronos2Forecaster,
    ForecastModelRegistry,
    ForecastModelSpec,
    TimesFMForecaster,
    _load_timesfm_2p5_model,
)
from app.services.kronos_forecaster import ForecastValues
from app.services.tiingo import KlinePoint


class FakeAdapter:
    async def predict(
        self,
        history: list[KlinePoint],
        forecast_timestamps: list[datetime],
        timeout_seconds: float,
    ) -> ForecastValues:
        return ForecastValues(open=[], high=[], low=[], close=[], volume=[])


def _point(year: int, month: int, day: int, **kwargs) -> KlinePoint:
    return KlinePoint(timestamp=datetime(year, month, day, tzinfo=UTC), **kwargs)


def _history() -> list[KlinePoint]:
    return [
        _point(2026, 5, 11, open=98.0, high=101.0, low=97.0, close=100.0, volume=1000.0),
        _point(2026, 5, 12, open=100.0, high=103.0, low=99.0, close=102.0, volume=1100.0),
        _point(2026, 5, 13, open=102.0, high=104.0, low=101.0, close=103.0, volume=1200.0),
    ]


def test_registry_preloads_and_reuses_one_instance_per_alias() -> None:
    created: list[str] = []
    specs = [
        ForecastModelSpec("one", "One", "model-one"),
        ForecastModelSpec("two", "Two", "model-two"),
    ]

    def factory(alias: str):
        def create() -> FakeAdapter:
            created.append(alias)
            return FakeAdapter()

        return create

    registry = ForecastModelRegistry(
        settings,
        specs=specs,
        factories={"one": factory("one"), "two": factory("two")},
    )

    assert created == []
    try:
        registry.get("one")
    except AppError:
        pass
    else:
        raise AssertionError("model should be unavailable before preload")

    asyncio.run(registry.load_all())
    first = registry.get("one")
    second = registry.get("one")
    third = registry.get("two")

    assert first is second
    assert third is not first
    assert created == ["one", "two"]


def test_app_startup_preloads_models_before_health_is_ready(monkeypatch) -> None:
    created: list[str] = []
    specs = [
        ForecastModelSpec("one", "One", "model-one"),
        ForecastModelSpec("two", "Two", "model-two"),
    ]

    def factory(alias: str):
        def create() -> FakeAdapter:
            created.append(alias)
            return FakeAdapter()

        return create

    monkeypatch.setattr("app.services.forecast_models.default_model_specs", lambda _: specs)
    monkeypatch.setattr(
        "app.services.forecast_models.default_model_factories",
        lambda _: {"one": factory("one"), "two": factory("two")},
    )

    app = create_app(load_model=True)
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert sorted(created) == ["one", "two"]


def test_chronos_adapter_maps_quantiles_to_close_band() -> None:
    class FakeChronosPipeline:
        def predict_df(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
            assert list(df.columns) == ["item_id", "timestamp", "target"]
            assert kwargs["prediction_length"] == 3
            assert kwargs["quantile_levels"] == [0.1, 0.5, 0.9]
            return pd.DataFrame(
                {
                    "item_id": ["ticker", "ticker", "ticker"],
                    "timestamp": pd.date_range("2026-05-14", periods=3),
                    "target_name": ["target", "target", "target"],
                    "predictions": [11.0, 12.0, 13.0],
                    "0.1": [9.0, 10.0, 11.0],
                    "0.5": [11.0, 12.0, 13.0],
                    "0.9": [14.0, 15.0, 16.0],
                }
            )

    forecaster = Chronos2Forecaster(FakeChronosPipeline(), settings)
    forecast = forecaster._predict_sync(
        _history(),
        [
            datetime(2026, 5, 14, tzinfo=UTC),
            datetime(2026, 5, 15, tzinfo=UTC),
            datetime(2026, 5, 18, tzinfo=UTC),
        ],
    )

    assert forecast.open == [11.0, 12.0, 13.0]
    assert forecast.close == [11.0, 12.0, 13.0]
    assert forecast.low == [9.0, 10.0, 11.0]
    assert forecast.high == [14.0, 15.0, 16.0]
    assert forecast.volume == [1200.0, 1200.0, 1200.0]


def test_timesfm_adapter_maps_point_forecast_and_quantile_bounds() -> None:
    class FakeTimesFM:
        def forecast(self, horizon: int, inputs: list[np.ndarray]):
            assert horizon == 3
            assert inputs[0].tolist() == [100.0, 102.0, 103.0]
            point = np.array([[11.0, 12.0, 13.0]])
            quantiles = np.zeros((1, 3, 10))
            quantiles[0, :, 1] = [9.0, 10.0, 11.0]
            quantiles[0, :, 9] = [14.0, 15.0, 16.0]
            return point, quantiles

    forecaster = TimesFMForecaster(FakeTimesFM(), settings)
    forecast = forecaster._predict_sync(
        _history(),
        [
            datetime(2026, 5, 14, tzinfo=UTC),
            datetime(2026, 5, 15, tzinfo=UTC),
            datetime(2026, 5, 18, tzinfo=UTC),
        ],
    )

    assert forecast.open == [11.0, 12.0, 13.0]
    assert forecast.close == [11.0, 12.0, 13.0]
    assert forecast.low == [9.0, 10.0, 11.0]
    assert forecast.high == [14.0, 15.0, 16.0]
    assert forecast.volume == [1200.0, 1200.0, 1200.0]


def test_timesfm_loader_avoids_hub_mixin_proxy_kwargs(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeTimesFM:
        _hub_mixin_init_parameters = {
            "self": object(),
            "torch_compile": object(),
            "config": object(),
        }

        @classmethod
        def _from_pretrained(cls, **kwargs):
            calls.append(kwargs)
            return cls()

    monkeypatch.setattr(
        "app.services.forecast_models._load_hub_config",
        lambda model_id: {"torch_compile": False, "ignored": "value"},
    )

    model = _load_timesfm_2p5_model(FakeTimesFM, "google/timesfm-2.5-200m-pytorch")

    assert isinstance(model, FakeTimesFM)
    assert calls == [
        {
            "model_id": "google/timesfm-2.5-200m-pytorch",
            "revision": None,
            "cache_dir": None,
            "force_download": False,
            "local_files_only": False,
            "token": None,
            "torch_compile": False,
            "config": {"torch_compile": False, "ignored": "value"},
        }
    ]
    assert "proxies" not in calls[0]
    assert "resume_download" not in calls[0]
