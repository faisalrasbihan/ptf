from fastapi import Request

from app.services.errors import AppError, ErrorCode
from app.services.forecast_models import ForecastModelRegistry


def get_model_registry(request: Request) -> ForecastModelRegistry:
    registry: ForecastModelRegistry | None = getattr(request.app.state, "model_registry", None)
    if registry is None:
        raise AppError(
            ErrorCode.MODEL_TIMEOUT,
            "Forecast models are not loaded.",
            503,
        )
    return registry
