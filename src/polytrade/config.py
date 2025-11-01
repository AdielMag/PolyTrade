from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Polymarket CLOB
    clob_host: str = Field(default="https://clob.polymarket.com", alias="CLOB_HOST")
    wallet_private_key: str | None = Field(default=None, alias="WALLET_PRIVATE_KEY")
    proxy_address: str | None = Field(default=None, alias="POLYMARKET_PROXY_ADDRESS")
    signature_type: int = Field(default=2, alias="SIGNATURE_TYPE")
    chain_id: int = Field(default=137, alias="CHAIN_ID")

    # Telegram
    bot_a_token: str | None = Field(default=None, alias="TELEGRAM_BOT_A_TOKEN")
    bot_b_token: str | None = Field(default=None, alias="TELEGRAM_BOT_B_TOKEN")
    bot_a_webhook_url: str | None = Field(default=None, alias="TELEGRAM_BOT_A_WEBHOOK_URL")
    bot_b_webhook_url: str | None = Field(default=None, alias="TELEGRAM_BOT_B_WEBHOOK_URL")
    bot_b_default_chat_id: int | None = Field(default=None, alias="BOT_B_DEFAULT_CHAT_ID")
    
    @field_validator("bot_b_default_chat_id", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: str | int | None) -> int | None:
        """Convert empty strings to None for optional integer fields."""
        if v == "" or v is None:
            return None
        return int(v) if isinstance(v, str) else v

    # Strategy
    edge_bps: int = Field(default=50, alias="EDGE_BPS")
    min_liquidity_usd: int = Field(default=1000, alias="MIN_LIQUIDITY_USD")
    default_sl_pct: float = Field(default=0.15, alias="DEFAULT_SL_PCT")
    default_tp_pct: float = Field(default=0.25, alias="DEFAULT_TP_PCT")

    # GCP
    gcp_project_id: str | None = Field(default=None, alias="GCP_PROJECT_ID")

    # Runtime app selector (Cloud Run)
    app_module: str | None = Field(default=None, alias="APP_MODULE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        populate_by_name = True


settings = Settings()  # Singleton-style import


