from fastapi import APIRouter

from app.api.debug import forecast


router = APIRouter(prefix="/debug")
router.include_router(forecast.router, tags=["debug"])
