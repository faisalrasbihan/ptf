from fastapi import Request

from app.core.config import settings
from app.services.forecast_models import ForecastModelRegistry


def get_model_registry(request: Request) -> ForecastModelRegistry:
    registry: ForecastModelRegistry | None = getattr(request.app.state, "model_registry", None)
    if registry is None:
        registry = ForecastModelRegistry(settings)
        request.app.state.model_registry = registry
    return registry
