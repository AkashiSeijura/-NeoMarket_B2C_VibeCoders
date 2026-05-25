from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = "NeoMarket B2C"
    database_url: str = "sqlite:///./neomarket_b2c.db"
    b2b_url: str = "http://localhost:8000"
    b2c_to_b2b_key: str = "dev-b2c-to-b2b-key"
    b2b_timeout_seconds: float = 3.0


settings = Settings(
    app_name=os.getenv("APP_NAME", "NeoMarket B2C"),
    database_url=os.getenv("DATABASE_URL", "sqlite:///./neomarket_b2c.db"),
    b2b_url=os.getenv("B2B_URL", "http://localhost:8000"),
    b2c_to_b2b_key=os.getenv("B2C_TO_B2B_KEY", "dev-b2c-to-b2b-key"),
    b2b_timeout_seconds=float(os.getenv("B2B_TIMEOUT_SECONDS", "3.0")),
)
