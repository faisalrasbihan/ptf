from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "ptf"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    TIINGO_KEY: str = ""
    REDIS_URL: str = ""
    TIINGO_CACHE_ENABLED: bool = True
    TIINGO_CACHE_NAMESPACE: str = "ptf:tiingo:v1"
    TIINGO_CACHE_STALE_AFTER_HOURS: int = 30
    TIINGO_CACHE_LOCK_SECONDS: int = 30
    KRONOS_MODEL_ID: str = "NeoQuasar/Kronos-mini"
    KRONOS_TOKENIZER_ID: str = "NeoQuasar/Kronos-Tokenizer-2k"
    KRONOS_MODEL_ALIAS: str = "kronos-mini"
    KRONOS_DEVICE: str = "cpu"
    KRONOS_MAX_CONTEXT: int = 2048
    KRONOS_TEMPERATURE: float = 1.0
    KRONOS_TOP_P: float = 0.9
    KRONOS_SAMPLE_COUNT: int = 1
    KRONOS_MINI_MODEL_ID: str = "NeoQuasar/Kronos-mini"
    KRONOS_MINI_TOKENIZER_ID: str = "NeoQuasar/Kronos-Tokenizer-2k"
    KRONOS_MINI_MODEL_ALIAS: str = "kronos-mini"
    KRONOS_MINI_MAX_CONTEXT: int = 2048
    KRONOS_SMALL_MODEL_ID: str = "NeoQuasar/Kronos-small"
    KRONOS_SMALL_TOKENIZER_ID: str = "NeoQuasar/Kronos-Tokenizer-base"
    KRONOS_SMALL_MODEL_ALIAS: str = "kronos-small"
    KRONOS_SMALL_MAX_CONTEXT: int = 512
    KRONOS_BASE_MODEL_ID: str = "NeoQuasar/Kronos-base"
    KRONOS_BASE_TOKENIZER_ID: str = "NeoQuasar/Kronos-Tokenizer-base"
    KRONOS_BASE_MODEL_ALIAS: str = "kronos-base"
    KRONOS_BASE_MAX_CONTEXT: int = 512
    CHRONOS_MODEL_ID: str = "amazon/chronos-2"
    CHRONOS_MODEL_ALIAS: str = "amazon-chronos-2"
    CHRONOS_DEVICE_MAP: str = "cpu"
    TIMESFM_MODEL_ID: str = "google/timesfm-2.5-200m-pytorch"
    TIMESFM_MODEL_ALIAS: str = "google-timesfm-2.5"
    TIMESFM_MAX_CONTEXT: int = 1024
    TIMESFM_MAX_HORIZON: int = 256
    MIN_FORECAST_DAYS: int = 5
    MAX_FORECAST_DAYS: int = 90
    TIINGO_TIMEOUT_SECONDS: float = 15.0
    MODEL_TIMEOUT_SECONDS: float = 60.0
    HISTORY_YEARS: int = 2
    DEBUG_ENDPOINTS_ENABLED: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
