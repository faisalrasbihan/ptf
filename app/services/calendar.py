from datetime import date, timedelta

import pandas_market_calendars as mcal

from app.services.errors import AppError, ErrorCode


CALENDAR_BY_EXCHANGE = {
    "XNAS": "NASDAQ",
    "XNYS": "NYSE",
}


def get_calendar_name(exchange: str) -> str:
    try:
        return CALENDAR_BY_EXCHANGE[exchange]
    except KeyError as exc:
        raise AppError(
            ErrorCode.BAD_REQUEST,
            f"Unsupported exchange '{exchange}'. Supported exchanges are XNAS and XNYS.",
            400,
        ) from exc


def next_trading_dates(exchange: str, last_history_date: date, days: int) -> list[date]:
    calendar = mcal.get_calendar(get_calendar_name(exchange))
    start = last_history_date + timedelta(days=1)
    end = start + timedelta(days=days * 3 + 14)

    schedule = calendar.schedule(start_date=start, end_date=end)
    sessions = [session.date() for session in schedule.index]

    while len(sessions) < days:
        end = end + timedelta(days=days)
        schedule = calendar.schedule(start_date=start, end_date=end)
        sessions = [session.date() for session in schedule.index]

    return sessions[:days]
