from fastapi import APIRouter, Request, Response

from app.api.dependencies import get_model_registry
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
    asset_type: str,
    horizon: str,
    model: str | None = None,
) -> Response:
    payload = ForecastRequest(ticker=ticker, asset_type=asset_type, model=model, horizon=horizon)
    forecast = await build_forecast_response(
        payload=payload,
        settings=settings,
        tiingo_provider=TiingoProvider(settings),
        model_registry=get_model_registry(request),
    )
    return Response(
        content=render_forecast_png(forecast),
        media_type="image/png",
    )
