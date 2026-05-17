import json
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from app.core.config import Settings

try:
    import redis.asyncio as redis_asyncio
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - exercised only when optional dependency is absent locally.
    redis_asyncio = None

    class RedisError(Exception):
        pass


TimeLike = date | datetime
PointFactory = Callable[[datetime, float, float, float, float, float], Any]

_CLIENTS: dict[str, Any] = {}


class TiingoHistoryCache:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.TIINGO_CACHE_ENABLED
            and self.settings.REDIS_URL
            and redis_asyncio is not None
        )

    def history_key(
        self,
        ticker: str,
        start_time: TimeLike,
        end_time: TimeLike,
        *,
        asset_type: str = "stock",
        bar_interval: str = "1d",
    ) -> str:
        return (
            f"{self.settings.TIINGO_CACHE_NAMESPACE}:history:"
            f"{asset_type}:{bar_interval}:{ticker.upper()}:"
            f"{_time_key(start_time)}:{_time_key(end_time)}:"
            f"years:{self.settings.HISTORY_YEARS}"
        )

    def lock_key(
        self,
        ticker: str,
        start_time: TimeLike,
        end_time: TimeLike,
        *,
        asset_type: str = "stock",
        bar_interval: str = "1d",
    ) -> str:
        return f"{self.history_key(ticker, start_time, end_time, asset_type=asset_type, bar_interval=bar_interval)}:lock"

    async def get_history(
        self,
        ticker: str,
        start_time: TimeLike,
        end_time: TimeLike,
        point_factory: PointFactory,
        *,
        asset_type: str = "stock",
        bar_interval: str = "1d",
    ) -> list[Any] | None:
        client = self._client()
        if client is None:
            return None

        key = self.history_key(ticker, start_time, end_time, asset_type=asset_type, bar_interval=bar_interval)
        try:
            raw_payload = await client.get(key)
        except RedisError:
            return None

        if raw_payload is None:
            return None

        try:
            return self._deserialize_history(
                raw_payload,
                ticker=ticker,
                start_time=start_time,
                end_time=end_time,
                asset_type=asset_type,
                bar_interval=bar_interval,
                point_factory=point_factory,
            )
        except (TypeError, ValueError, json.JSONDecodeError, KeyError):
            await self.delete_history(ticker, start_time, end_time, asset_type=asset_type, bar_interval=bar_interval)
            return None

    async def set_history(
        self,
        ticker: str,
        start_time: TimeLike,
        end_time: TimeLike,
        history: list[Any],
        *,
        asset_type: str = "stock",
        bar_interval: str = "1d",
    ) -> None:
        client = self._client()
        if client is None:
            return

        key = self.history_key(ticker, start_time, end_time, asset_type=asset_type, bar_interval=bar_interval)
        payload = self._serialize_history(
            ticker,
            start_time,
            end_time,
            history,
            asset_type=asset_type,
            bar_interval=bar_interval,
        )
        try:
            await client.set(key, payload, ex=self._ttl_seconds())
        except RedisError:
            return

    async def delete_history(
        self,
        ticker: str,
        start_time: TimeLike,
        end_time: TimeLike,
        *,
        asset_type: str = "stock",
        bar_interval: str = "1d",
    ) -> None:
        client = self._client()
        if client is None:
            return

        try:
            await client.delete(self.history_key(ticker, start_time, end_time, asset_type=asset_type, bar_interval=bar_interval))
        except RedisError:
            return

    async def acquire_lock(
        self,
        ticker: str,
        start_time: TimeLike,
        end_time: TimeLike,
        *,
        asset_type: str = "stock",
        bar_interval: str = "1d",
    ) -> str | None:
        client = self._client()
        if client is None:
            return None

        token = uuid.uuid4().hex
        try:
            locked = await client.set(
                self.lock_key(ticker, start_time, end_time, asset_type=asset_type, bar_interval=bar_interval),
                token,
                nx=True,
                ex=max(1, self.settings.TIINGO_CACHE_LOCK_SECONDS),
            )
        except RedisError:
            return None

        return token if locked else None

    async def release_lock(
        self,
        ticker: str,
        start_time: TimeLike,
        end_time: TimeLike,
        token: str,
        *,
        asset_type: str = "stock",
        bar_interval: str = "1d",
    ) -> None:
        client = self._client()
        if client is None:
            return

        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] "
            "then return redis.call('del', KEYS[1]) else return 0 end"
        )
        try:
            await client.eval(script, 1, self.lock_key(ticker, start_time, end_time, asset_type=asset_type, bar_interval=bar_interval), token)
        except RedisError:
            return

    def _client(self) -> Any | None:
        if not self.enabled:
            return None

        url = self.settings.REDIS_URL
        client = _CLIENTS.get(url)
        if client is None:
            client = redis_asyncio.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
            )
            _CLIENTS[url] = client
        return client

    def _ttl_seconds(self) -> int:
        return max(1, self.settings.TIINGO_CACHE_STALE_AFTER_HOURS * 60 * 60)

    def _serialize_history(
        self,
        ticker: str,
        start_time: TimeLike,
        end_time: TimeLike,
        history: list[Any],
        *,
        asset_type: str = "stock",
        bar_interval: str = "1d",
    ) -> str:
        payload = {
            "ticker": ticker.upper(),
            "asset_type": asset_type,
            "bar_interval": bar_interval,
            "start_time": _time_key(start_time),
            "end_time": _time_key(end_time),
            "history_years": self.settings.HISTORY_YEARS,
            "cached_at": datetime.now(UTC).isoformat(),
            "bars": [
                {
                    "date": point.date.isoformat(),
                    "timestamp": point.timestamp.isoformat(),
                    "open": float(point.open),
                    "high": float(point.high),
                    "low": float(point.low),
                    "close": float(point.close),
                    "volume": float(point.volume),
                }
                for point in history
            ],
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)

    def _deserialize_history(
        self,
        raw_payload: str | bytes,
        *,
        ticker: str,
        start_time: TimeLike,
        end_time: TimeLike,
        asset_type: str,
        bar_interval: str,
        point_factory: PointFactory,
    ) -> list[Any]:
        if isinstance(raw_payload, bytes):
            raw_payload = raw_payload.decode("utf-8")

        payload = json.loads(raw_payload)
        if not isinstance(payload, dict):
            raise ValueError("Cache payload must be an object.")

        if payload.get("ticker") != ticker.upper():
            raise ValueError("Cache ticker mismatch.")
        if payload.get("asset_type") != asset_type:
            raise ValueError("Cache asset type mismatch.")
        if payload.get("bar_interval") != bar_interval:
            raise ValueError("Cache bar interval mismatch.")
        if payload.get("start_time") != _time_key(start_time):
            raise ValueError("Cache start time mismatch.")
        if payload.get("end_time") != _time_key(end_time):
            raise ValueError("Cache end time mismatch.")
        if payload.get("history_years") != self.settings.HISTORY_YEARS:
            raise ValueError("Cache history window mismatch.")

        bars = payload.get("bars")
        if not isinstance(bars, list):
            raise ValueError("Cache bars must be a list.")

        history = []
        for item in bars:
            if not isinstance(item, dict):
                raise ValueError("Cache bar must be an object.")
            history.append(
                point_factory(
                    datetime.fromisoformat(str(item["timestamp"])),
                    float(item["open"]),
                    float(item["high"]),
                    float(item["low"]),
                    float(item["close"]),
                    float(item["volume"]),
                )
            )
        return history


def _time_key(value: TimeLike) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()
