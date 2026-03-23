import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    postgres_host: str
    postgres_port: int
    postgres_user: str
    postgres_password: str
    postgres_db: str
    targets_csv_path: str
    forecast_days: int
    open_meteo_base: str
    http_timeout_s: float

    @property
    def pg_dsn(self) -> str:
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"dbname={self.postgres_db} user={self.postgres_user} "
            f"password={self.postgres_password}"
        )


def load_settings() -> Settings:
    return Settings(
        postgres_host=os.environ.get("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.environ.get("POSTGRES_PORT", "5432")),
        postgres_user=os.environ["POSTGRES_USER"],
        postgres_password=os.environ["POSTGRES_PASSWORD"],
        postgres_db=os.environ["POSTGRES_DB"],
        targets_csv_path=os.environ.get(
            "TARGETS_CSV_PATH",
            "/data/targets/city_targets.csv",
        ),
        forecast_days=int(os.environ.get("OPEN_METEO_FORECAST_DAYS", "3")),
        open_meteo_base=os.environ.get(
            "OPEN_METEO_BASE",
            "https://api.open-meteo.com/v1/forecast",
        ),
        http_timeout_s=float(os.environ.get("HTTP_TIMEOUT_S", "30")),
    )
