import asyncio
from dataclasses import dataclass
from datetime import date

import pandas as pd
from model import Kronos, KronosPredictor, KronosTokenizer

from app.core.config import Settings
from app.services.errors import AppError, ErrorCode
from app.services.tiingo import KlinePoint


@dataclass(slots=True)
class ForecastValues:
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float]


class KronosForecaster:
    def __init__(self, predictor: KronosPredictor, settings: Settings):
        self.predictor = predictor
        self.settings = settings

    @classmethod
    def from_settings(cls, settings: Settings) -> "KronosForecaster":
        tokenizer = KronosTokenizer.from_pretrained(settings.KRONOS_TOKENIZER_ID)
        model = Kronos.from_pretrained(settings.KRONOS_MODEL_ID)
        predictor = KronosPredictor(
            model,
            tokenizer,
            device=settings.KRONOS_DEVICE,
            max_context=settings.KRONOS_MAX_CONTEXT,
        )
        return cls(predictor, settings)

    async def predict(
        self,
        history: list[KlinePoint],
        forecast_dates: list[date],
        timeout_seconds: float,
    ) -> ForecastValues:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._predict_sync, history, forecast_dates),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise AppError(
                ErrorCode.MODEL_TIMEOUT,
                "Forecast model timed out.",
                504,
            ) from exc
        except Exception as exc:
            raise AppError(
                ErrorCode.MODEL_TIMEOUT,
                "Forecast model failed to generate a forecast.",
                504,
            ) from exc

    def _predict_sync(
        self,
        history: list[KlinePoint],
        forecast_dates: list[date],
    ) -> ForecastValues:
        context = history[-self.settings.KRONOS_MAX_CONTEXT :]
        x_df = pd.DataFrame(
            {
                "open": [point.open for point in context],
                "high": [point.high for point in context],
                "low": [point.low for point in context],
                "close": [point.close for point in context],
                "volume": [point.volume for point in context],
            }
        )
        x_timestamp = pd.Series(pd.to_datetime([point.date for point in context]))
        y_timestamp = pd.Series(pd.to_datetime(forecast_dates))

        pred_df = self.predictor.predict(
            df=x_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=len(forecast_dates),
            T=self.settings.KRONOS_TEMPERATURE,
            top_p=self.settings.KRONOS_TOP_P,
            sample_count=self.settings.KRONOS_SAMPLE_COUNT,
            verbose=False,
        )

        opens: list[float] = []
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        volumes: list[float] = []
        for _, row in pred_df.iterrows():
            open_price = float(row["open"])
            close = float(row["close"])
            low = float(row["low"])
            high = float(row["high"])
            opens.append(open_price)
            highs.append(max(open_price, close, low, high))
            lows.append(min(open_price, close, low, high))
            closes.append(close)
            volumes.append(max(float(row.get("volume", 0.0)), 0.0))

        return ForecastValues(
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            volume=volumes,
        )
