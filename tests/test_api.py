import json
from datetime import date

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.forecast_models import ForecastModelSpec
from app.services.kronos_forecaster import ForecastValues
from app.services.tiingo import KlinePoint
from app.services.errors import AppError, ErrorCode


def _parse_sse_events(payload: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for block in payload.strip().split("\n\n"):
        event = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            if line.startswith("data: "):
                data_lines.append(line.removeprefix("data: "))
        if data_lines:
            events.append((event, json.loads("\n".join(data_lines))))
    return events


class FakeModelRegistry:
    specs = [
        ForecastModelSpec("kronos-mini", "Kronos Mini", "NeoQuasar/Kronos-mini"),
        ForecastModelSpec("kronos-small", "Kronos Small", "NeoQuasar/Kronos-small"),
        ForecastModelSpec("kronos-base", "Kronos Base", "NeoQuasar/Kronos-base"),
        ForecastModelSpec("amazon-chronos-2", "Amazon Chronos-2", "amazon/chronos-2"),
        ForecastModelSpec("google-timesfm-2.5", "Google TimesFM 2.5", "google/timesfm-2.5-200m-pytorch"),
    ]

    def resolve(self, alias: str | None) -> ForecastModelSpec:
        model_alias = alias or "kronos-mini"
        for spec in self.specs:
            if spec.alias == model_alias:
                return spec
        raise AppError(ErrorCode.BAD_REQUEST, f"Unsupported model '{model_alias}'.", 400)

    async def predict(
        self,
        model_alias: str,
        history: list[KlinePoint],
        forecast_dates: list[date],
        timeout_seconds: float,
    ) -> ForecastValues:
        days = len(forecast_dates)
        return ForecastValues(
            open=[float(value) + 0.25 for value in range(days)],
            high=[float(value) + 1 for value in range(days)],
            low=[value - 1 for value in range(days)],
            close=[float(value) for value in range(days)],
            volume=[1000.0 + value for value in range(days)],
        )


def test_post_forecast_success(monkeypatch) -> None:
    async def fake_fetch_history(self, ticker: str) -> list[KlinePoint]:
        return [
            KlinePoint(date=date(2026, 5, 13), open=183.0, high=185.0, low=182.5, close=184.1, volume=1000),
            KlinePoint(date=date(2026, 5, 14), open=184.0, high=186.0, low=183.5, close=185.2, volume=1200),
        ]

    monkeypatch.setattr(
        "app.services.tiingo.TiingoProvider.fetch_history",
        fake_fetch_history,
    )

    app = create_app(load_model=False)
    app.state.model_registry = FakeModelRegistry()

    with TestClient(app) as client:
        response = client.post("/forecast", json={"ticker": " aapl ", "days": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert "exchange" not in body
    assert body["model"] == "kronos-mini"
    assert body["days"] == 5
    assert body["history"][0] == {
        "date": "2026-05-13",
        "open": 183.0,
        "high": 185.0,
        "low": 182.5,
        "close": 184.1,
        "volume": 1000.0,
    }
    assert len(body["forecast"]) == 5
    assert body["forecast"][0]["date"] == "2026-05-15"
    assert body["forecast"][0] == {
        "date": "2026-05-15",
        "open": 0.25,
        "high": 1.0,
        "low": -1.0,
        "close": 0.0,
        "volume": 1000.0,
        "median": 0.0,
    }


def test_get_forecast_models_lists_supported_aliases() -> None:
    app = create_app(load_model=False)
    app.state.model_registry = FakeModelRegistry()

    with TestClient(app) as client:
        response = client.get("/forecast/models")

    assert response.status_code == 200
    assert response.json() == {
        "models": [
            {
                "alias": "kronos-mini",
                "display_name": "Kronos Mini",
                "model_id": "NeoQuasar/Kronos-mini",
            },
            {
                "alias": "kronos-small",
                "display_name": "Kronos Small",
                "model_id": "NeoQuasar/Kronos-small",
            },
            {
                "alias": "kronos-base",
                "display_name": "Kronos Base",
                "model_id": "NeoQuasar/Kronos-base",
            },
            {
                "alias": "amazon-chronos-2",
                "display_name": "Amazon Chronos-2",
                "model_id": "amazon/chronos-2",
            },
            {
                "alias": "google-timesfm-2.5",
                "display_name": "Google TimesFM 2.5",
                "model_id": "google/timesfm-2.5-200m-pytorch",
            },
        ]
    }


def test_post_forecast_accepts_chronos_model(monkeypatch) -> None:
    async def fake_fetch_history(self, ticker: str) -> list[KlinePoint]:
        return [
            KlinePoint(date=date(2026, 5, 13), open=183.0, high=185.0, low=182.5, close=184.1, volume=1000),
            KlinePoint(date=date(2026, 5, 14), open=184.0, high=186.0, low=183.5, close=185.2, volume=1200),
        ]

    monkeypatch.setattr("app.services.tiingo.TiingoProvider.fetch_history", fake_fetch_history)
    app = create_app(load_model=False)
    app.state.model_registry = FakeModelRegistry()

    with TestClient(app) as client:
        response = client.post("/forecast", json={"ticker": "aapl", "days": 5, "model": "amazon-chronos-2"})

    assert response.status_code == 200
    assert response.json()["model"] == "amazon-chronos-2"


def test_post_forecast_accepts_timesfm_model(monkeypatch) -> None:
    async def fake_fetch_history(self, ticker: str) -> list[KlinePoint]:
        return [
            KlinePoint(date=date(2026, 5, 13), open=183.0, high=185.0, low=182.5, close=184.1, volume=1000),
            KlinePoint(date=date(2026, 5, 14), open=184.0, high=186.0, low=183.5, close=185.2, volume=1200),
        ]

    monkeypatch.setattr("app.services.tiingo.TiingoProvider.fetch_history", fake_fetch_history)
    app = create_app(load_model=False)
    app.state.model_registry = FakeModelRegistry()

    with TestClient(app) as client:
        response = client.post("/forecast", json={"ticker": "aapl", "days": 5, "model": "google-timesfm-2.5"})

    assert response.status_code == 200
    assert response.json()["model"] == "google-timesfm-2.5"


def test_post_forecast_streams_progress_and_result(monkeypatch) -> None:
    async def fake_fetch_history(self, ticker: str) -> list[KlinePoint]:
        return [
            KlinePoint(date=date(2026, 5, 13), open=183.0, high=185.0, low=182.5, close=184.1, volume=1000),
            KlinePoint(date=date(2026, 5, 14), open=184.0, high=186.0, low=183.5, close=185.2, volume=1200),
        ]

    monkeypatch.setattr(
        "app.services.tiingo.TiingoProvider.fetch_history",
        fake_fetch_history,
    )

    app = create_app(load_model=False)
    app.state.model_registry = FakeModelRegistry()

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/forecast",
            headers={"Accept": "text/event-stream"},
            json={"ticker": "aapl", "days": 5},
        ) as response:
            body = response.read().decode()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse_events(body)
    progress_phases = [data["phase"] for event, data in events if event == "progress"]
    assert progress_phases == [
        "validating_request",
        "model_selected",
        "fetching_history",
        "history_ready",
        "building_calendar",
        "calendar_ready",
        "preparing_model_input",
        "running_model",
        "model_complete",
        "formatting_response",
    ]

    result = next(data for event, data in events if event == "result")
    assert result["ticker"] == "AAPL"
    assert len(result["forecast"]) == 5
    assert events[-1] == (
        "complete",
        {
            "phase": "complete",
            "message": "Forecast ready.",
            "percent": 100,
        },
    )


def test_post_forecast_validation_error_uses_error_envelope() -> None:
    app = create_app(load_model=False)
    app.state.model_registry = FakeModelRegistry()

    with TestClient(app) as client:
        response = client.post("/forecast", json={"ticker": ""})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == ErrorCode.BAD_REQUEST


def test_post_forecast_streams_expected_error(monkeypatch) -> None:
    async def fake_fetch_history(self, ticker: str) -> list[KlinePoint]:
        raise AppError(
            ErrorCode.TICKER_NOT_FOUND,
            f"No data found for ticker '{ticker}'.",
            404,
        )

    monkeypatch.setattr(
        "app.services.tiingo.TiingoProvider.fetch_history",
        fake_fetch_history,
    )

    app = create_app(load_model=False)
    app.state.model_registry = FakeModelRegistry()

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/forecast",
            headers={"Accept": "text/event-stream"},
            json={"ticker": "XYZ"},
        ) as response:
            body = response.read().decode()

    assert response.status_code == 200
    events = _parse_sse_events(body)
    assert events[-1] == (
        "error",
        {
            "phase": "fetching_history",
            "code": ErrorCode.TICKER_NOT_FOUND,
            "message": "No data found for ticker 'XYZ'.",
        },
    )


def test_post_forecast_expected_error_uses_error_envelope(monkeypatch) -> None:
    async def fake_fetch_history(self, ticker: str) -> list[KlinePoint]:
        raise AppError(
            ErrorCode.TICKER_NOT_FOUND,
            f"No data found for ticker '{ticker}'.",
            404,
        )

    monkeypatch.setattr(
        "app.services.tiingo.TiingoProvider.fetch_history",
        fake_fetch_history,
    )

    app = create_app(load_model=False)
    app.state.model_registry = FakeModelRegistry()

    with TestClient(app) as client:
        response = client.post("/forecast", json={"ticker": "XYZ"})

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": ErrorCode.TICKER_NOT_FOUND,
            "message": "No data found for ticker 'XYZ'.",
        }
    }
