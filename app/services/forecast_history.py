from __future__ import annotations

import math

from app.services.errors import AppError, ErrorCode
from app.services.tiingo import KlinePoint


def prepare_history(
    history: list[KlinePoint],
    *,
    require_ohlcv: bool,
    min_points: int = 2,
) -> list[KlinePoint]:
    deduped = {point.timestamp: point for point in history}
    cleaned = [point for _, point in sorted(deduped.items()) if _is_valid_point(point, require_ohlcv)]
    if len(cleaned) < min_points:
        raise AppError(
            ErrorCode.DATA_SOURCE_ERROR,
            "Not enough valid history to generate a forecast.",
            502,
        )
    return cleaned


def last_finite_volume(history: list[KlinePoint]) -> float:
    for point in reversed(history):
        if math.isfinite(point.volume):
            return max(float(point.volume), 0.0)
    return 0.0


def _is_valid_point(point: KlinePoint, require_ohlcv: bool) -> bool:
    if not math.isfinite(point.close):
        return False
    if not require_ohlcv:
        return True
    return all(
        math.isfinite(value)
        for value in (
            point.open,
            point.high,
            point.low,
            point.close,
            point.volume,
        )
    )
