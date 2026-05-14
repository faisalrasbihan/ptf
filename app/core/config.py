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
    DEFAULT_FORECAST_DAYS: int = 30
    MIN_FORECAST_DAYS: int = 5
    MAX_FORECAST_DAYS: int = 90
    TIINGO_TIMEOUT_SECONDS: float = 15.0
    MODEL_TIMEOUT_SECONDS: float = 60.0
    HISTORY_YEARS: int = 2
    DEBUG_ENDPOINTS_ENABLED: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
