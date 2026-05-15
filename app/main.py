from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings
from app.services.errors import AppError, ErrorCode
from app.services.forecast_models import ForecastModelRegistry


def create_app(
    load_model: bool = True,
    debug_endpoints_enabled: bool | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if load_model:
            app.state.model_registry = ForecastModelRegistry(settings)
        yield

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
    )

    app.include_router(router)
    if debug_endpoints_enabled if debug_endpoints_enabled is not None else settings.DEBUG_ENDPOINTS_ENABLED:
        from app.api.debug import router as debug_router

        app.include_router(debug_router)

    @app.exception_handler(AppError)
    async def app_error_handler(_: object, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: object, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": ErrorCode.BAD_REQUEST,
                    "message": "Invalid request payload.",
                }
            },
        )

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    return app


app = create_app()
