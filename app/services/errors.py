from dataclasses import dataclass


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int


class ErrorCode:
    BAD_REQUEST = "BAD_REQUEST"
    TICKER_NOT_FOUND = "TICKER_NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    DATA_SOURCE_ERROR = "DATA_SOURCE_ERROR"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
