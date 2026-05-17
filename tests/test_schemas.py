import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.forecast import ForecastRequest
from app.services.errors import AppError, ErrorCode
from app.services.forecast import resolve_request
from app.services.forecast_models import ForecastModelRegistry


def _registry() -> ForecastModelRegistry:
    return ForecastModelRegistry(settings)


def test_forecast_request_defaults_and_normalizes() -> None:
    payload = ForecastRequest(ticker=" aapl ", asset_type="STOCK", model="", horizon="10D")
    resolved = resolve_request(payload, settings, _registry())

    assert resolved.ticker == "AAPL"
    assert resolved.asset_type == "stock"
    assert resolved.model_alias == "kronos-mini"
    assert resolved.horizon == "10d"
    assert resolved.forecast_steps == 10
    assert resolved.bar_interval == "1d"


@pytest.mark.parametrize(
    "model_alias",
    ["kronos-mini", "kronos-small", "kronos-base", "amazon-chronos-2", "google-timesfm-2.5"],
)
def test_resolve_request_accepts_supported_models(model_alias: str) -> None:
    payload = ForecastRequest(ticker="AAPL", asset_type="stock", model=model_alias, horizon="5d")

    resolved = resolve_request(payload, settings, _registry())

    assert resolved.model_alias == model_alias
    assert resolved.forecast_steps == 5


def test_forecast_request_rejects_empty_ticker() -> None:
    with pytest.raises(ValidationError):
        ForecastRequest(ticker="   ", asset_type="stock", horizon="5d")


def test_forecast_request_rejects_missing_asset_type() -> None:
    with pytest.raises(ValidationError):
        ForecastRequest(ticker="AAPL", horizon="5d")


def test_forecast_request_rejects_missing_horizon() -> None:
    with pytest.raises(ValidationError):
        ForecastRequest(ticker="AAPL", asset_type="stock")


def test_forecast_request_rejects_old_days_field() -> None:
    with pytest.raises(ValidationError):
        ForecastRequest(ticker="AAPL", asset_type="stock", horizon="5d", days=5)


def test_resolve_request_rejects_out_of_range_days() -> None:
    payload = ForecastRequest(ticker="AAPL", asset_type="stock", horizon="4d")

    with pytest.raises(AppError) as exc:
        resolve_request(payload, settings, _registry())

    assert exc.value.code == ErrorCode.BAD_REQUEST


@pytest.mark.parametrize(
    ("horizon", "bar_interval", "forecast_steps"),
    [("1h", "1h", 1), ("4h", "1h", 4), ("24h", "1h", 24), ("7d", "4h", 42)],
)
def test_resolve_request_accepts_crypto_horizons(
    horizon: str,
    bar_interval: str,
    forecast_steps: int,
) -> None:
    payload = ForecastRequest(ticker="btc/usd", asset_type="crypto", horizon=horizon)

    resolved = resolve_request(payload, settings, _registry())

    assert resolved.ticker == "BTCUSD"
    assert resolved.asset_type == "crypto"
    assert resolved.horizon == horizon
    assert resolved.bar_interval == bar_interval
    assert resolved.forecast_steps == forecast_steps


def test_resolve_request_rejects_unsupported_model() -> None:
    payload = ForecastRequest(ticker="AAPL", asset_type="stock", horizon="5d", model="chronos-bolt-small")

    with pytest.raises(AppError) as exc:
        resolve_request(payload, settings, _registry())

    assert exc.value.code == ErrorCode.BAD_REQUEST
