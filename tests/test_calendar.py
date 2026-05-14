from datetime import date

from app.services.calendar import next_us_trading_dates


def test_next_us_trading_dates_skip_weekend() -> None:
    dates = next_us_trading_dates(date(2026, 5, 15), 3)

    assert dates == [
        date(2026, 5, 18),
        date(2026, 5, 19),
        date(2026, 5, 20),
    ]


def test_next_us_trading_dates_skip_us_market_holiday() -> None:
    dates = next_us_trading_dates(date(2026, 5, 22), 2)

    assert dates == [
        date(2026, 5, 26),
        date(2026, 5, 27),
    ]
