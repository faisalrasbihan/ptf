from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "ptf"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    TIINGO_KEY: str = ""
    KRONOS_MODEL_ID: str = "NeoQuasar/Kronos-base"
    KRONOS_TOKENIZER_ID: str = "NeoQuasar/Kronos-Tokenizer-base"
    KRONOS_MODEL_ALIAS: str = "kronos-base"
    KRONOS_DEVICE: str = "cpu"
    KRONOS_MAX_CONTEXT: int = 512
    KRONOS_TEMPERATURE: float = 1.0
    KRONOS_TOP_P: float = 0.9
    KRONOS_SAMPLE_COUNT: int = 1
    CHRONOS_MODEL_ID: str = "amazon/chronos-2"
    CHRONOS_MODEL_ALIAS: str = "amazon-chronos-2"
    CHRONOS_DEVICE_MAP: str = "cpu"
    TIMESFM_MODEL_ID: str = "google/timesfm-2.5-200m-pytorch"
    TIMESFM_MODEL_ALIAS: str = "google-timesfm-2.5"
    TIMESFM_MAX_CONTEXT: int = 1024
    TIMESFM_MAX_HORIZON: int = 256
    DEFAULT_FORECAST_DAYS: int = 30
    MIN_FORECAST_DAYS: int = 5
    MAX_FORECAST_DAYS: int = 90
    TIINGO_TIMEOUT_SECONDS: float = 15.0
    MODEL_TIMEOUT_SECONDS: float = 60.0
    HISTORY_YEARS: int = 2
    DEBUG_ENDPOINTS_ENABLED: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
