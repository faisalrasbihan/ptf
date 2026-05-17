# Security Policy

## Supported versions

This project is pre-1.0. Security fixes are handled on the main development line unless a release branch is explicitly created later.

## Reporting a vulnerability

Please do not open a public issue for security vulnerabilities.

If the repository host supports private vulnerability reporting, use that first. Otherwise, contact the maintainer privately and include enough detail to reproduce the issue.

Useful details include:

- Affected endpoint or file.
- Steps to reproduce.
- Impact and likely severity.
- Whether credentials, API keys, user data, or model artifacts are exposed.
- Any suggested fix, if you have one.

## Scope

Security-sensitive areas in this project include:

- Handling of `TIINGO_KEY` and other environment variables.
- Server-Sent Events streaming behavior.
- External HTTP calls to Tiingo.
- Model loading and model artifact paths.
- Debug endpoints enabled by `DEBUG_ENDPOINTS_ENABLED`.
- Deployment configuration and logs.

## Out of scope

Please avoid reports for:

- Missing features that do not create a security risk.
- Public information about third-party model or data-provider behavior.
- Denial-of-service claims that rely only on sending large volumes of normal traffic without a specific vulnerability.

## Responsible disclosure

Give maintainers a reasonable chance to investigate and fix confirmed issues before public disclosure. Please do not include live secrets, private API keys, or sensitive market-data credentials in reports.
