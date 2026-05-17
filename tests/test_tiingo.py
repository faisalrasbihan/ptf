import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services import tiingo_cache
from app.services.errors import AppError, ErrorCode
from app.services.tiingo_cache import TiingoHistoryCache
from app.services.tiingo import KlinePoint, TiingoProvider


def make_response(status_code: int, payload: object) -> httpx.Response:
    request = httpx.Request("GET", "https://example.test")
    return httpx.Response(status_code, json=payload, request=request)


def point_at(year: int, month: int, day: int, hour: int = 0, **kwargs: object) -> KlinePoint:
    return KlinePoint(timestamp=datetime(year, month, day, hour, tzinfo=UTC), **kwargs)


class FrozenDate(date):
    @classmethod
    def today(cls) -> date:
        return cls(2026, 5, 17)


class FakeRedis:
    def __init__(self, initial: dict[str, str] | None = None, fail: bool = False):
        self.store = dict(initial or {})
        self.expirations: dict[str, int | None] = {}
        self.deleted: list[str] = []
        self.fail = fail

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise tiingo_cache.RedisError("redis unavailable")
        return self.store.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        if self.fail:
            raise tiingo_cache.RedisError("redis unavailable")
        if nx and key in self.store:
            return False
        self.store[key] = value
        self.expirations[key] = ex
        return True

    async def delete(self, key: str) -> int:
        if self.fail:
            raise tiingo_cache.RedisError("redis unavailable")
        self.deleted.append(key)
        existed = key in self.store
        self.store.pop(key, None)
        return 1 if existed else 0

    async def eval(self, script: str, keys_count: int, key: str, token: str) -> int:
        if self.fail:
            raise tiingo_cache.RedisError("redis unavailable")
        if self.store.get(key) == token:
            await self.delete(key)
            return 1
        return 0


class FakeRedisModule:
    def __init__(self, client: FakeRedis):
        self.client = client

    def from_url(self, url: str, **kwargs: Any) -> FakeRedis:
        return self.client


@pytest.fixture(autouse=True)
def configure_tiingo_test_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TIINGO_KEY", "test-tiingo-key")
    monkeypatch.setattr(settings, "REDIS_URL", "")
    monkeypatch.setattr(settings, "TIINGO_CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "TIINGO_CACHE_NAMESPACE", "ptf:tiingo:v1")
    monkeypatch.setattr(settings, "TIINGO_CACHE_STALE_AFTER_HOURS", 30)
    monkeypatch.setattr(settings, "TIINGO_CACHE_LOCK_SECONDS", 30)
    monkeypatch.setattr(settings, "HISTORY_YEARS", 2)
    tiingo_cache._CLIENTS.clear()


def enable_fake_redis(monkeypatch: pytest.MonkeyPatch, client: FakeRedis) -> None:
    tiingo_cache._CLIENTS.clear()
    monkeypatch.setattr(settings, "REDIS_URL", "redis://cache.test/0")
    monkeypatch.setattr(tiingo_cache, "redis_asyncio", FakeRedisModule(client))


def test_tiingo_provider_parses_history(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        assert str(args[0]).endswith("/tiingo/daily/aapl/prices")
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

    history = asyncio.run(TiingoProvider(settings).fetch_history("AAPL"))

    assert [(point.date, point.open, point.high, point.low, point.close, point.volume) for point in history] == [
        (date(2026, 5, 12), 7.5, 8.2, 7.0, 8.0, 900.0),
        (date(2026, 5, 13), 8.5, 10.5, 8.0, 9.5, 1100.0),
    ]


def test_tiingo_provider_fetches_and_parses_crypto_history(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        assert str(args[0]) == "https://api.tiingo.com/tiingo/crypto/prices"
        params = kwargs["params"]
        assert params["tickers"] == "btcusd"
        assert params["resampleFreq"] == "1hour"
        return make_response(
            200,
            [
                {
                    "ticker": "btcusd",
                    "baseCurrency": "btc",
                    "quoteCurrency": "usd",
                    "priceData": [
                        {
                            "date": "2026-05-15T09:00:00.000Z",
                            "open": 100.0,
                            "high": 103.0,
                            "low": 99.0,
                            "close": 102.0,
                            "volume": 12.5,
                            "volumeNotional": 1275.0,
                        },
                        {
                            "date": "2026-05-15T10:00:00.000Z",
                            "open": 102.0,
                            "high": 104.0,
                            "low": 101.0,
                            "close": 103.0,
                            "volume": 13.5,
                        },
                    ],
                }
            ],
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    history = asyncio.run(
        TiingoProvider(settings).fetch_history("BTCUSD", asset_type="crypto", bar_interval="1h")
    )

    assert [(point.timestamp, point.close, point.volume) for point in history] == [
        (datetime(2026, 5, 15, 9, tzinfo=UTC), 102.0, 12.5),
        (datetime(2026, 5, 15, 10, tzinfo=UTC), 103.0, 13.5),
    ]


def test_tiingo_provider_maps_empty_crypto_price_data_to_ticker_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        return make_response(200, [{"ticker": "btcusd", "priceData": []}])

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(AppError) as exc:
        asyncio.run(TiingoProvider(settings).fetch_history("BTCUSD", asset_type="crypto", bar_interval="1h"))

    assert exc.value.code == ErrorCode.TICKER_NOT_FOUND


def test_tiingo_provider_uses_cached_history_without_calling_tiingo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.tiingo.date", FrozenDate)
    cache = TiingoHistoryCache(settings)
    end_date = FrozenDate.today()
    start_date = end_date - timedelta(days=365 * settings.HISTORY_YEARS)
    cached_history = [
        point_at(2026, 5, 15, open=10.0, high=12.0, low=9.0, close=11.0, volume=1000.0)
    ]
    redis = FakeRedis(
        {
            cache.history_key("AAPL", start_date, end_date): cache._serialize_history(
                "AAPL",
                start_date,
                end_date,
                cached_history,
            )
        }
    )
    enable_fake_redis(monkeypatch, redis)

    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        raise AssertionError("Tiingo should not be called on a cache hit.")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    history = asyncio.run(TiingoProvider(settings).fetch_history("aapl"))

    assert history == cached_history


def test_tiingo_provider_stores_history_after_cache_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.tiingo.date", FrozenDate)
    redis = FakeRedis()
    enable_fake_redis(monkeypatch, redis)

    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        return make_response(
            200,
            [
                {
                    "date": "2026-05-15T00:00:00.000Z",
                    "open": 10.0,
                    "high": 12.0,
                    "low": 9.0,
                    "close": 11.0,
                    "volume": 1000,
                }
            ],
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    history = asyncio.run(TiingoProvider(settings).fetch_history("AAPL"))

    end_date = FrozenDate.today()
    start_date = end_date - timedelta(days=365 * settings.HISTORY_YEARS)
    key = TiingoHistoryCache(settings).history_key("AAPL", start_date, end_date)
    cached_payload = json.loads(redis.store[key])
    assert history == [
        point_at(2026, 5, 15, open=10.0, high=12.0, low=9.0, close=11.0, volume=1000.0)
    ]
    assert cached_payload["ticker"] == "AAPL"
    assert cached_payload["asset_type"] == "stock"
    assert cached_payload["bar_interval"] == "1d"
    assert cached_payload["start_time"] == start_date.isoformat()
    assert cached_payload["end_time"] == end_date.isoformat()
    assert cached_payload["history_years"] == 2
    assert cached_payload["bars"] == [
        {
            "date": "2026-05-15",
            "timestamp": "2026-05-15T00:00:00+00:00",
            "open": 10.0,
            "high": 12.0,
            "low": 9.0,
            "close": 11.0,
            "volume": 1000.0,
        }
    ]
    assert redis.expirations[key] == 30 * 60 * 60


def test_tiingo_provider_falls_back_to_tiingo_when_redis_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.tiingo.date", FrozenDate)
    redis = FakeRedis(fail=True)
    enable_fake_redis(monkeypatch, redis)

    async def no_sleep(seconds: float) -> None:
        return None

    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        return make_response(
            200,
            [
                {
                    "date": "2026-05-15T00:00:00.000Z",
                    "open": 10.0,
                    "high": 12.0,
                    "low": 9.0,
                    "close": 11.0,
                    "volume": 1000,
                }
            ],
        )

    monkeypatch.setattr("app.services.tiingo.asyncio.sleep", no_sleep)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    history = asyncio.run(TiingoProvider(settings).fetch_history("AAPL"))

    assert history == [
        point_at(2026, 5, 15, open=10.0, high=12.0, low=9.0, close=11.0, volume=1000.0)
    ]


def test_tiingo_provider_ignores_malformed_cache_and_refreshes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.tiingo.date", FrozenDate)
    cache = TiingoHistoryCache(settings)
    end_date = FrozenDate.today()
    start_date = end_date - timedelta(days=365 * settings.HISTORY_YEARS)
    key = cache.history_key("AAPL", start_date, end_date)
    redis = FakeRedis({key: "not-json"})
    enable_fake_redis(monkeypatch, redis)

    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        return make_response(
            200,
            [
                {
                    "date": "2026-05-15T00:00:00.000Z",
                    "open": 10.0,
                    "high": 12.0,
                    "low": 9.0,
                    "close": 11.0,
                    "volume": 1000,
                }
            ],
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    history = asyncio.run(TiingoProvider(settings).fetch_history("AAPL"))

    assert history == [
        point_at(2026, 5, 15, open=10.0, high=12.0, low=9.0, close=11.0, volume=1000.0)
    ]
    assert key in redis.deleted
    assert json.loads(redis.store[key])["bars"][0]["date"] == "2026-05-15"


def test_tiingo_cache_key_includes_date_window_and_history_years(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "REDIS_URL", "redis://cache.test/0")
    cache = TiingoHistoryCache(settings)

    first_key = cache.history_key("AAPL", date(2026, 1, 1), date(2026, 5, 17))
    second_key = cache.history_key("AAPL", date(2026, 1, 1), date(2026, 5, 18))
    monkeypatch.setattr(settings, "HISTORY_YEARS", 3)
    third_key = cache.history_key("AAPL", date(2026, 1, 1), date(2026, 5, 17))

    assert first_key == "ptf:tiingo:v1:history:stock:1d:AAPL:2026-01-01:2026-05-17:years:2"
    assert second_key != first_key
    assert third_key != first_key


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
        asyncio.run(TiingoProvider(settings).fetch_history("AAPL"))

    assert exc.value.code == expected_code


def test_tiingo_provider_maps_empty_data_to_ticker_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        return make_response(200, [])

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(AppError) as exc:
        asyncio.run(TiingoProvider(settings).fetch_history("AAPL"))

    assert exc.value.code == ErrorCode.TICKER_NOT_FOUND


def test_tiingo_provider_maps_malformed_shape_to_data_source_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self: httpx.AsyncClient, *args: object, **kwargs: object) -> httpx.Response:
        return make_response(200, {"unexpected": True})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    with pytest.raises(AppError) as exc:
        asyncio.run(TiingoProvider(settings).fetch_history("AAPL"))

    assert exc.value.code == ErrorCode.DATA_SOURCE_ERROR
