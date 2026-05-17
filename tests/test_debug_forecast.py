from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.forecast_models import ForecastModelSpec
from app.services.kronos_forecaster import ForecastValues
from app.services.tiingo import KlinePoint


class FakeModelRegistry:
    specs = [ForecastModelSpec("kronos-mini", "Kronos Mini", "NeoQuasar/Kronos-mini")]

    def resolve(self, alias: str | None) -> ForecastModelSpec:
        return self.specs[0]

    async def predict(
        self,
        model_alias: str,
        history: list[KlinePoint],
        forecast_timestamps: list[datetime],
        timeout_seconds: float,
    ) -> ForecastValues:
        days = len(forecast_timestamps)
        return ForecastValues(
            open=[103.0 + index for index in range(days)],
            high=[106.0 + index for index in range(days)],
            low=[102.0 + index for index in range(days)],
            close=[104.0 + index for index in range(days)],
            volume=[1000.0 + index for index in range(days)],
        )


def test_debug_forecast_route_is_disabled_by_default() -> None:
    app = create_app(load_model=False, debug_endpoints_enabled=False)

    with TestClient(app) as client:
        response = client.get("/debug/forecast/AAPL")

    assert response.status_code == 404


def test_debug_forecast_route_returns_png_when_enabled(monkeypatch) -> None:
    async def fake_fetch_history(self, ticker: str, **kwargs) -> list[KlinePoint]:
        return [
            KlinePoint(timestamp=datetime(2026, 5, 13, tzinfo=UTC), open=99.0, high=101.0, low=98.0, close=100.0, volume=1000),
            KlinePoint(timestamp=datetime(2026, 5, 14, tzinfo=UTC), open=100.0, high=102.0, low=99.0, close=101.0, volume=1200),
        ]

    monkeypatch.setattr(
        "app.services.tiingo.TiingoProvider.fetch_history",
        fake_fetch_history,
    )

    app = create_app(load_model=False, debug_endpoints_enabled=True)
    app.state.model_registry = FakeModelRegistry()

    with TestClient(app) as client:
        response = client.get("/debug/forecast/aapl?asset_type=stock&horizon=5d")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG")
