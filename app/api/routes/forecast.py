from fastapi import APIRouter, Request

from app.api.dependencies import get_forecaster
from app.core.config import settings
from app.schemas.forecast import ForecastRequest, ForecastResponse
from app.services.forecast import build_forecast_response
from app.services.tiingo import TiingoProvider


router = APIRouter()


@router.post("", response_model=ForecastResponse)
async def create_forecast(payload: ForecastRequest, request: Request) -> ForecastResponse:
    return await build_forecast_response(
        payload=payload,
        settings=settings,
        tiingo_provider=TiingoProvider(settings),
        forecaster=get_forecaster(request),
    )
