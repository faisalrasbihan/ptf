from datetime import UTC, date, datetime, time, timedelta

import pandas_market_calendars as mcal


US_MARKET_CALENDAR = "NYSE"


def next_us_trading_dates(last_history_date: date, days: int) -> list[date]:
    calendar = mcal.get_calendar(US_MARKET_CALENDAR)
    start = last_history_date + timedelta(days=1)
    end = start + timedelta(days=days * 3 + 14)

    schedule = calendar.schedule(start_date=start, end_date=end)
    sessions = [session.date() for session in schedule.index]

    while len(sessions) < days:
        end = end + timedelta(days=days)
        schedule = calendar.schedule(start_date=start, end_date=end)
        sessions = [session.date() for session in schedule.index]

    return sessions[:days]


def next_us_trading_timestamps(last_history_timestamp: datetime, days: int) -> list[datetime]:
    return [
        datetime.combine(session, time.min, tzinfo=UTC)
        for session in next_us_trading_dates(last_history_timestamp.date(), days)
    ]


def next_continuous_timestamps(
    last_history_timestamp: datetime,
    *,
    steps: int,
    step: timedelta,
) -> list[datetime]:
    return [last_history_timestamp + step * index for index in range(1, steps + 1)]
