import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.forecast import ForecastRequest
from app.services.errors import AppError, ErrorCode
from app.services.forecast import resolve_request


def test_forecast_request_defaults_and_normalizes() -> None:
    payload = ForecastRequest(ticker=" aapl ", exchange="", model="", days="")
    resolved = resolve_request(payload, settings)

    assert resolved.ticker == "AAPL"
    assert resolved.exchange == "XNAS"
    assert resolved.model_alias == "kronos-base"
    assert resolved.days == 30


def test_forecast_request_rejects_empty_ticker() -> None:
    with pytest.raises(ValidationError):
        ForecastRequest(ticker="   ")


def test_resolve_request_rejects_out_of_range_days() -> None:
    payload = ForecastRequest(ticker="AAPL", days=4)

    with pytest.raises(AppError) as exc:
        resolve_request(payload, settings)

    assert exc.value.code == ErrorCode.BAD_REQUEST


def test_resolve_request_rejects_unsupported_model() -> None:
    payload = ForecastRequest(ticker="AAPL", model="chronos-bolt-small")

    with pytest.raises(AppError) as exc:
        resolve_request(payload, settings)

    assert exc.value.code == ErrorCode.BAD_REQUEST


def test_resolve_request_rejects_unsupported_exchange() -> None:
    payload = ForecastRequest(ticker="AAPL", exchange="XLON")

    with pytest.raises(AppError) as exc:
        resolve_request(payload, settings)

    assert exc.value.code == ErrorCode.BAD_REQUEST
