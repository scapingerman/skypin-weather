from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CityTarget:
    city_id: int
    city_name: str
    country_code: str
    latitude: float
    longitude: float
    alert_rain_mm_h: float
    min_precip_prob_pct: int


def load_city_targets(path: str) -> list[CityTarget]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Targets CSV not found: {p}")
    rows: list[CityTarget] = []
    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rows.append(
                CityTarget(
                    city_id=int(raw["city_id"]),
                    city_name=raw["city_name"].strip(),
                    country_code=raw.get("country_code", "AR").strip(),
                    latitude=float(raw["latitude"]),
                    longitude=float(raw["longitude"]),
                    alert_rain_mm_h=float(raw["alert_rain_mm_h"]),
                    min_precip_prob_pct=int(raw["min_precip_prob_pct"]),
                )
            )
    if not rows:
        raise ValueError("Targets CSV has no data rows")
    return rows
