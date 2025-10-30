from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Polymarket/API
    polymarket_api_base: str = Field(default="https://api.polymarket.com", alias="POLYMARKET_API_BASE")
    polymarket_api_key: str | None = Field(default=None, alias="POLYMARKET_API_KEY")

    # Telegram
    bot_a_token: str | None = Field(default=None, alias="TELEGRAM_BOT_A_TOKEN")
    bot_b_token: str | None = Field(default=None, alias="TELEGRAM_BOT_B_TOKEN")
    bot_a_webhook_url: str | None = Field(default=None, alias="TELEGRAM_BOT_A_WEBHOOK_URL")
    bot_b_webhook_url: str | None = Field(default=None, alias="TELEGRAM_BOT_B_WEBHOOK_URL")
    bot_b_default_chat_id: int | None = Field(default=None, alias="BOT_B_DEFAULT_CHAT_ID")

    # Strategy
    edge_bps: int = Field(default=50, alias="EDGE_BPS")
    min_liquidity_usd: int = Field(default=1000, alias="MIN_LIQUIDITY_USD")
    default_sl_pct: float = Field(default=0.15, alias="DEFAULT_SL_PCT")
    default_tp_pct: float = Field(default=0.25, alias="DEFAULT_TP_PCT")

    # GCP
    firestore_project_id: str | None = Field(default=None, alias="FIRESTORE_PROJECT_ID")

    # Runtime app selector (Cloud Run)
    app_module: str | None = Field(default=None, alias="APP_MODULE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        populate_by_name = True


settings = Settings()  # Singleton-style import


