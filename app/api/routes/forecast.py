import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_forecaster
from app.core.config import settings
from app.schemas.forecast import ForecastRequest, ForecastResponse
from app.services.errors import AppError
from app.services.forecast import build_forecast_response
from app.services.tiingo import TiingoProvider


router = APIRouter()


@router.post("", response_model=ForecastResponse)
async def create_forecast(
    payload: ForecastRequest,
    request: Request,
) -> ForecastResponse | StreamingResponse:
    if "text/event-stream" in request.headers.get("accept", ""):
        return _forecast_stream_response(payload, request)

    return await build_forecast_response(
        payload=payload,
        settings=settings,
        tiingo_provider=TiingoProvider(settings),
        forecaster=get_forecaster(request),
    )


@router.post("/stream")
async def create_forecast_stream(payload: ForecastRequest, request: Request) -> StreamingResponse:
    return _forecast_stream_response(payload, request)


def _forecast_stream_response(payload: ForecastRequest, request: Request) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        progress_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        last_progress: dict[str, object] = {
            "phase": "queued",
            "message": "Forecast request queued.",
            "percent": 0,
        }

        async def report_progress(phase: str, message: str, percent: int) -> None:
            await progress_queue.put(
                {
                    "phase": phase,
                    "message": message,
                    "percent": percent,
                }
            )

        forecast_task = asyncio.create_task(
            build_forecast_response(
                payload=payload,
                settings=settings,
                tiingo_provider=TiingoProvider(settings),
                forecaster=get_forecaster(request),
                progress=report_progress,
            )
        )

        try:
            while True:
                if await request.is_disconnected():
                    forecast_task.cancel()
                    return

                if forecast_task.done() and progress_queue.empty():
                    break

                try:
                    progress = await asyncio.wait_for(progress_queue.get(), timeout=5)
                except asyncio.TimeoutError:
                    if not forecast_task.done():
                        yield _format_sse(
                            "progress",
                            {
                                "phase": last_progress["phase"],
                                "message": "Still working on the current forecast phase.",
                                "percent": last_progress["percent"],
                            },
                        )
                    continue

                last_progress = progress
                yield _format_sse("progress", progress)

            try:
                forecast = forecast_task.result()
            except AppError as exc:
                yield _format_sse(
                    "error",
                    {
                        "phase": last_progress["phase"],
                        "code": exc.code,
                        "message": exc.message,
                    },
                )
                return

            yield _format_sse("result", json.loads(forecast.model_dump_json()))
            yield _format_sse(
                "complete",
                {
                    "phase": "complete",
                    "message": "Forecast ready.",
                    "percent": 100,
                },
            )
        finally:
            if not forecast_task.done():
                forecast_task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _format_sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"
