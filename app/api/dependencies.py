from fastapi import Request

from app.core.config import settings
from app.services.kronos_forecaster import KronosForecaster


def get_forecaster(request: Request) -> KronosForecaster:
    forecaster: KronosForecaster | None = getattr(request.app.state, "forecaster", None)
    if forecaster is None:
        forecaster = KronosForecaster.from_settings(settings)
        request.app.state.forecaster = forecaster
    return forecaster
