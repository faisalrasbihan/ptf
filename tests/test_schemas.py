import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.forecast import ForecastRequest
from app.services.errors import AppError, ErrorCode
from app.services.forecast import resolve_request


def test_forecast_request_defaults_and_normalizes() -> None:
    payload = ForecastRequest(ticker=" aapl ", model="", days="")
    resolved = resolve_request(payload, settings)

    assert resolved.ticker == "AAPL"
    assert resolved.model_alias == "kronos-base"
    assert resolved.days == 30


@pytest.mark.parametrize("model_alias", ["kronos-base", "amazon-chronos-2", "google-timesfm-2.5"])
def test_resolve_request_accepts_supported_models(model_alias: str) -> None:
    payload = ForecastRequest(ticker="AAPL", model=model_alias, days=5)

    resolved = resolve_request(payload, settings)

    assert resolved.model_alias == model_alias
    assert resolved.days == 5


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
