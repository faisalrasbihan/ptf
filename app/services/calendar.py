from datetime import date, timedelta

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
