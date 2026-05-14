import asyncio
from datetime import date

import httpx
import pytest

from app.core.config import settings
from app.services.errors import AppError, ErrorCode
from app.services.tiingo import TiingoProvider


def make_response(status_code: int, payload: object) -> httpx.Response:
    request = httpx.Request("GET", "https://example.test")
    return httpx.Response(status_code, json=payload, request=request)


def test_tiingo_provider_parses_history(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        return make_response(
            200,
            [
                {
                    "date": "2026-05-13T00:00:00.000Z",
                    "open": 9.0,
                    "high": 11.0,
                    "low": 8.5,
                    "close": 10.0,
                    "adjOpen": 8.5,
                    "adjHigh": 10.5,
                    "adjLow": 8.0,
                    "adjClose": 9.5,
                    "volume": 1000,
                    "adjVolume": 1100,
                },
                {
                    "date": "2026-05-12T00:00:00.000Z",
                    "open": 7.5,
                    "high": 8.2,
                    "low": 7.0,
                    "close": 8.0,
                    "volume": 900,
                },
                {"date": "2026-05-14T00:00:00.000Z"},
            ],
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    history = asyncio.run(TiingoProvider(settings).fetch_history("AAPL", "XNAS"))

    assert [(point.date, point.open, point.high, point.low, point.close, point.volume) for point in history] == [
        (date(2026, 5, 12), 7.5, 8.2, 7.0, 8.0, 900.0),
        (date(2026, 5, 13), 8.5, 10.5, 8.0, 9.5, 1100.0),
    ]


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (404, ErrorCode.TICKER_NOT_FOUND),
        (429, ErrorCode.RATE_LIMITED),
        (500, ErrorCode.DATA_SOURCE_ERROR),
    ],
)
def test_tiingo_provider_maps_status_codes(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_code: str,
) -> None:
    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        return make_response(status_code, {"detail": "nope"})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(AppError) as exc:
        asyncio.run(TiingoProvider(settings).fetch_history("AAPL", "XNAS"))

    assert exc.value.code == expected_code


def test_tiingo_provider_maps_empty_data_to_ticker_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        return make_response(200, [])

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(AppError) as exc:
        asyncio.run(TiingoProvider(settings).fetch_history("AAPL", "XNAS"))

    assert exc.value.code == ErrorCode.TICKER_NOT_FOUND


def test_tiingo_provider_maps_malformed_shape_to_data_source_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        return make_response(200, {"unexpected": True})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(AppError) as exc:
        asyncio.run(TiingoProvider(settings).fetch_history("AAPL", "XNAS"))

    assert exc.value.code == ErrorCode.DATA_SOURCE_ERROR
