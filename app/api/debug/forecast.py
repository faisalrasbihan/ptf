from fastapi import APIRouter, Request, Response

from app.api.dependencies import get_forecaster
from app.core.config import settings
from app.schemas.forecast import ForecastRequest
from app.services.debug_chart import render_forecast_png
from app.services.forecast import build_forecast_response
from app.services.tiingo import TiingoProvider


router = APIRouter()


@router.get("/forecast/{ticker}", response_class=Response)
async def debug_forecast_chart(
    ticker: str,
    request: Request,
    model: str | None = None,
    days: str | None = None,
) -> Response:
    payload = ForecastRequest(ticker=ticker, model=model, days=days)
    forecast = await build_forecast_response(
        payload=payload,
        settings=settings,
        tiingo_provider=TiingoProvider(settings),
        forecaster=get_forecaster(request),
    )
    return Response(
        content=render_forecast_png(forecast),
        media_type="image/png",
    )
