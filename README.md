# predictthefuture.xyz

An open-source forecasting service for exploring what time-series foundation models predict for public stock prices, and how uncertain those predictions are.

The project is intentionally framed as an educational and research-oriented tool. Stock prices are noisy, daily direction is often close to a random walk, and the useful part of a forecast is usually the uncertainty band rather than a single confident-looking number. This repository leans into that: it fetches recent market history, runs a forecasting model, labels the forecast with real trading dates, and returns history plus forecast data in one API response.

> Not financial advice. Forecasts from this project are illustrative only and should not be used as investment recommendations.

## What is in this repository?

This repo currently contains the Python/FastAPI forecasting backend for predictthefuture.xyz.

The backend owns the full pipeline:

1. Validate a ticker, model alias, and forecast horizon.
2. Fetch adjusted daily OHLCV history from Tiingo.
3. Generate future NYSE trading dates.
4. Run a time-series foundation model.
5. Return historical prices, forecast values, and a confidence-style band in a frontend-friendly shape.

The planned product is a single-page web app with a thin frontend and this service behind it. The frontend can call this API directly or through a pass-through route.

## Features

- FastAPI service with typed Pydantic request and response schemas.
- Tiingo daily adjusted OHLCV data provider.
- NYSE trading-calendar support via `pandas-market-calendars`.
- Model registry with support for:
  - `kronos-mini`
  - `kronos-small`
  - `kronos-base`
  - `amazon-chronos-2`
  - `google-timesfm-2.5`
- JSON forecast endpoint.
- Server-Sent Events forecast endpoint for progress updates.
- Fixed error response shape for frontend mapping.
- Optional debug PNG forecast chart endpoint.
- Test coverage for API behavior, schemas, calendar handling, Tiingo parsing, and model adapters.
- Railway-oriented start command via `railpack.json`.

## Architecture

```text
Client or frontend
      |
      |  POST /forecast
      v
FastAPI service
      |
      |-- Fetch adjusted daily OHLCV history from Tiingo
      |-- Build future NYSE trading sessions
      |-- Run selected forecasting model
      |-- Shape history + forecast response
      v
JSON or Server-Sent Events response
```

The service deliberately keeps data fetching and inference together. That makes the API simple for clients: a request contains only the ticker and optional knobs, not a full price history payload.

## API

### Health check

```http
GET /health
```

```json
{
  "status": "ok"
}
```

### List available models

```http
GET /forecast/models
```

```json
{
  "models": [
    {
      "alias": "kronos-base",
      "display_name": "Kronos Base",
      "model_id": "NeoQuasar/Kronos-base"
    }
  ]
}
```

### Create a forecast

```http
POST /forecast
Content-Type: application/json
```

```json
{
  "ticker": "AAPL",
  "model": "kronos-base",
  "days": 30
}
```

Fields:

- `ticker`: required. Normalized to uppercase.
- `model`: optional. Defaults to the configured `KRONOS_MODEL_ALIAS`.
- `days`: optional. Defaults to `DEFAULT_FORECAST_DAYS`. Must be between `MIN_FORECAST_DAYS` and `MAX_FORECAST_DAYS`.

Example response:

```json
{
  "ticker": "AAPL",
  "history": [
    {
      "date": "2026-05-13",
      "open": 183.0,
      "high": 185.0,
      "low": 182.5,
      "close": 184.1,
      "volume": 1000.0
    }
  ],
  "forecast": [
    {
      "date": "2026-05-14",
      "open": 184.62,
      "high": 188.04,
      "low": 181.09,
      "close": 184.62,
      "volume": 1000.0,
      "median": 184.62
    }
  ],
  "model": "kronos-base",
  "days": 30,
  "generated_at": "2026-05-14T12:00:00Z"
}
```

### Stream progress

Use either endpoint:

```http
POST /forecast/stream
Accept: text/event-stream
```

or:

```http
POST /forecast
Accept: text/event-stream
```

Events include:

- `progress`: phase, message, and percent.
- `result`: final forecast response.
- `complete`: completion marker.
- `error`: fixed-shape error payload if the request fails.

### Error shape

Errors are returned consistently:

```json
{
  "error": {
    "code": "TICKER_NOT_FOUND",
    "message": "No data found for ticker 'XYZ'."
  }
}
```

Current error codes:

- `BAD_REQUEST`
- `TICKER_NOT_FOUND`
- `RATE_LIMITED`
- `DATA_SOURCE_ERROR`
- `MODEL_TIMEOUT`

## Local development

### Prerequisites

- Python 3.11+
- A Tiingo API key
- Enough memory and disk space for model dependencies and downloaded model weights

The ML dependencies are substantial. First startup can take a while because model weights may be downloaded and loaded.

### Setup

```bash
python -m venv ptf
source ptf/bin/activate
pip install -r requirements.txt
```

Create a local `.env` file:

```bash
TIINGO_KEY=your_tiingo_api_key

# Optional overrides
KRONOS_MODEL_ALIAS=kronos-base
DEFAULT_FORECAST_DAYS=30
MIN_FORECAST_DAYS=5
MAX_FORECAST_DAYS=90
MODEL_TIMEOUT_SECONDS=60
DEBUG_ENDPOINTS_ENABLED=false
```

Start the API:

```bash
uvicorn app.main:app --reload
```

The service will be available at:

```text
http://127.0.0.1:8000
```

Try a forecast:

```bash
curl -s http://127.0.0.1:8000/forecast \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","model":"kronos-base","days":30}'
```

## Configuration

Configuration is loaded from environment variables and `.env` through Pydantic settings.

Common settings:

| Variable | Default | Purpose |
|---|---:|---|
| `TIINGO_KEY` | empty | Tiingo API token. Required for real data fetches. |
| `DEFAULT_FORECAST_DAYS` | `30` | Default forecast horizon in trading days. |
| `MIN_FORECAST_DAYS` | `5` | Minimum accepted horizon. |
| `MAX_FORECAST_DAYS` | `90` | Maximum accepted horizon. |
| `HISTORY_YEARS` | `2` | Lookback window fetched from Tiingo. |
| `MODEL_TIMEOUT_SECONDS` | `60` | Inference timeout. |
| `DEBUG_ENDPOINTS_ENABLED` | `false` | Enables debug chart routes. |
| `KRONOS_DEVICE` | `cpu` | Device used by Kronos. |
| `CHRONOS_DEVICE_MAP` | `cpu` | Device map used by Chronos. |

Model IDs and aliases can also be overridden with the variables defined in `app/core/config.py`.

## Debug chart endpoint

When `DEBUG_ENDPOINTS_ENABLED=true`, the service exposes:

```http
GET /debug/forecast/{ticker}?model=kronos-base&days=30
```

It returns a PNG chart rendered from the forecast response. This is useful for quick backend-only visual checks.

## Tests

Run the test suite with:

```bash
pytest
```

The tests mostly use fakes and monkeypatches, so they are designed to validate API behavior and data-shaping logic without requiring live Tiingo calls or full model inference.

## Deployment

The repository includes a Railway/Railpack start command:

```json
{
  "deploy": {
    "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
  }
}
```

For production, configure at least:

- `TIINGO_KEY`
- model/device settings appropriate for the host
- enough RAM for the selected model set
- a strategy for model weight caching or baked images, so restarts do not repeatedly pull large files

## Project structure

```text
app/
  api/
    routes/          Forecast API routes
    debug/           Optional debug chart route
  core/              Settings
  schemas/           Pydantic request/response models
  services/          Tiingo, calendar, forecasting, model adapters
tests/               API and service tests
railpack.json        Railway start command
requirements.txt     Python dependencies
```

## Roadmap

- Add the public frontend for predictthefuture.xyz.
- Tighten model-loading configuration so deployments can choose a smaller model set.
- Add caching near the Tiingo fetch and model inference pipeline.
- Add richer uncertainty output where models expose real quantiles.
- Explore volatility forecasting as a more statistically grounded next step.
- Add provider abstractions beyond Tiingo if licensing and coverage require it.

## Contributing

Issues and pull requests are welcome.

See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, testing, and pull request guidance. Please also read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Security issues should be reported privately according to [SECURITY.md](SECURITY.md).

Good first areas to help with:

- Better local setup docs for different hardware profiles.
- More tests around model adapter edge cases.
- Frontend integration examples.
- Deployment recipes.
- Clearer responsible-use language.

Please keep changes honest about the limits of price forecasting. The goal is not to make forecasts look more certain than they are.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
