# Contributing

Thanks for considering a contribution to predictthefuture.xyz. This project is early, so clear bug reports, setup improvements, tests, and careful API changes are all genuinely useful.

## Project principles

- Be honest about forecasting limits. The project should never imply that a model forecast is investment advice.
- Keep the API simple for clients. The backend owns the ticker-to-data-to-model pipeline.
- Prefer typed, tested changes over broad rewrites.
- Keep secrets out of commits. Use `.env`, and update `.env.example` when configuration changes.

## Local setup

```bash
python -m venv ptf
source ptf/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your Tiingo API key to `.env`:

```bash
TIINGO_KEY=your_tiingo_api_key_here
```

Start the API:

```bash
uvicorn app.main:app --reload
```

The service should be available at `http://127.0.0.1:8000`.

## Running tests

```bash
pytest
```

If you are using the local virtualenv created above and `pytest` is not on your shell path, run:

```bash
ptf/bin/pytest
```

Most tests use fakes and monkeypatches, so they should not require a Tiingo key or live model inference.

## Good first contributions

- Improve setup and deployment documentation.
- Add tests for edge cases in model adapters, Tiingo parsing, and API error handling.
- Improve debug tooling for backend-only forecast inspection.
- Add frontend integration examples.
- Clarify responsible-use language.

## Pull request checklist

Before opening a pull request:

- Run the test suite.
- Update documentation when behavior, endpoints, environment variables, or setup steps change.
- Include or update tests for user-facing behavior.
- Keep unrelated formatting or refactors out of the PR.
- Note any API schema changes clearly in the PR description.

## Reporting issues

When reporting a bug, include:

- The endpoint or command you ran.
- The request payload, with secrets removed.
- The expected behavior.
- The actual behavior and error response.
- Your Python version and operating system.

For security issues, do not open a public issue. See `SECURITY.md`.
