from datetime import date

import pytest

from app.services.calendar import next_trading_dates
from app.services.errors import AppError, ErrorCode


def test_next_trading_dates_skip_weekend() -> None:
    dates = next_trading_dates("XNAS", date(2026, 5, 15), 3)

    assert dates == [
        date(2026, 5, 18),
        date(2026, 5, 19),
        date(2026, 5, 20),
    ]


def test_next_trading_dates_skip_us_market_holiday() -> None:
    dates = next_trading_dates("XNAS", date(2026, 5, 22), 2)

    assert dates == [
        date(2026, 5, 26),
        date(2026, 5, 27),
    ]


def test_next_trading_dates_rejects_unsupported_exchange() -> None:
    with pytest.raises(AppError) as exc:
        next_trading_dates("XLON", date(2026, 5, 15), 1)

    assert exc.value.code == ErrorCode.BAD_REQUEST
