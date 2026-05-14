import asyncio
from datetime import date

import pandas as pd

from app.core.config import settings
from app.services.kronos_forecaster import KronosForecaster
from app.services.tiingo import KlinePoint


class FakePredictor:
    def predict(
        self,
        df: pd.DataFrame,
        x_timestamp: pd.Series,
        y_timestamp: pd.Series,
        pred_len: int,
        T: float,
        top_p: float,
        sample_count: int,
        verbose: bool,
    ) -> pd.DataFrame:
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert pred_len == 3
        return pd.DataFrame(
            {
                "open": [10.0, 11.0, 12.0],
                "high": [12.0, 13.0, 14.0],
                "low": [9.0, 10.0, 11.0],
                "close": [11.0, 12.0, 13.0],
                "volume": [100.0, 110.0, 120.0],
                "amount": [1000.0, 1100.0, 1200.0],
            },
            index=y_timestamp,
        )


def test_kronos_forecaster_maps_ohlc_to_forecast_band() -> None:
    forecaster = KronosForecaster(FakePredictor(), settings)
    history = [
        KlinePoint(date=date(2026, 5, 11), open=7.0, high=8.0, low=6.0, close=7.5, volume=1000),
        KlinePoint(date=date(2026, 5, 12), open=8.0, high=9.0, low=7.0, close=8.5, volume=1200),
    ]
    forecast_dates = [date(2026, 5, 13), date(2026, 5, 14), date(2026, 5, 15)]

    forecast = asyncio.run(forecaster.predict(history, forecast_dates, 1.0))

    assert forecast.open == [10.0, 11.0, 12.0]
    assert forecast.high == [12.0, 13.0, 14.0]
    assert forecast.low == [9.0, 10.0, 11.0]
    assert forecast.close == [11.0, 12.0, 13.0]
    assert forecast.volume == [100.0, 110.0, 120.0]
