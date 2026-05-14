from fastapi import APIRouter

from app.api.routes import forecast

router = APIRouter()
router.include_router(forecast.router, prefix="/forecast", tags=["forecast"])
