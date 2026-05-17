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


PointFactory = Callable[[date, float, float, float, float, float], Any]

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

    def history_key(self, ticker: str, start_date: date, end_date: date) -> str:
        return (
            f"{self.settings.TIINGO_CACHE_NAMESPACE}:history:"
            f"{ticker.upper()}:{start_date.isoformat()}:{end_date.isoformat()}:"
            f"years:{self.settings.HISTORY_YEARS}"
        )

    def lock_key(self, ticker: str, start_date: date, end_date: date) -> str:
        return f"{self.history_key(ticker, start_date, end_date)}:lock"

    async def get_history(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        point_factory: PointFactory,
    ) -> list[Any] | None:
        client = self._client()
        if client is None:
            return None

        key = self.history_key(ticker, start_date, end_date)
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
                start_date=start_date,
                end_date=end_date,
                point_factory=point_factory,
            )
        except (TypeError, ValueError, json.JSONDecodeError, KeyError):
            await self.delete_history(ticker, start_date, end_date)
            return None

    async def set_history(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        history: list[Any],
    ) -> None:
        client = self._client()
        if client is None:
            return

        key = self.history_key(ticker, start_date, end_date)
        payload = self._serialize_history(ticker, start_date, end_date, history)
        try:
            await client.set(key, payload, ex=self._ttl_seconds())
        except RedisError:
            return

    async def delete_history(self, ticker: str, start_date: date, end_date: date) -> None:
        client = self._client()
        if client is None:
            return

        try:
            await client.delete(self.history_key(ticker, start_date, end_date))
        except RedisError:
            return

    async def acquire_lock(self, ticker: str, start_date: date, end_date: date) -> str | None:
        client = self._client()
        if client is None:
            return None

        token = uuid.uuid4().hex
        try:
            locked = await client.set(
                self.lock_key(ticker, start_date, end_date),
                token,
                nx=True,
                ex=max(1, self.settings.TIINGO_CACHE_LOCK_SECONDS),
            )
        except RedisError:
            return None

        return token if locked else None

    async def release_lock(self, ticker: str, start_date: date, end_date: date, token: str) -> None:
        client = self._client()
        if client is None:
            return

        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] "
            "then return redis.call('del', KEYS[1]) else return 0 end"
        )
        try:
            await client.eval(script, 1, self.lock_key(ticker, start_date, end_date), token)
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
        start_date: date,
        end_date: date,
        history: list[Any],
    ) -> str:
        payload = {
            "ticker": ticker.upper(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "history_years": self.settings.HISTORY_YEARS,
            "cached_at": datetime.now(UTC).isoformat(),
            "bars": [
                {
                    "date": point.date.isoformat(),
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
        start_date: date,
        end_date: date,
        point_factory: PointFactory,
    ) -> list[Any]:
        if isinstance(raw_payload, bytes):
            raw_payload = raw_payload.decode("utf-8")

        payload = json.loads(raw_payload)
        if not isinstance(payload, dict):
            raise ValueError("Cache payload must be an object.")

        if payload.get("ticker") != ticker.upper():
            raise ValueError("Cache ticker mismatch.")
        if payload.get("start_date") != start_date.isoformat():
            raise ValueError("Cache start date mismatch.")
        if payload.get("end_date") != end_date.isoformat():
            raise ValueError("Cache end date mismatch.")
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
                    date.fromisoformat(str(item["date"])),
                    float(item["open"]),
                    float(item["high"]),
                    float(item["low"]),
                    float(item["close"]),
                    float(item["volume"]),
                )
            )
        return history
