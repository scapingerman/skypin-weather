"""Risk rules aligned with mart.mart_city_hourly_risk (refresh_downstream.sql)."""

from __future__ import annotations

STORM_CODES = frozenset({95, 96, 99})


def hourly_risk(
    precipitation: float | None,
    precipitation_probability: int | None,
    weathercode: int | None,
    alert_rain_mm_h: float,
    min_precip_prob_pct: int,
) -> tuple[bool, float]:
    p = float(precipitation or 0.0)
    prob = int(precipitation_probability or 0)
    code = int(weathercode or 0)
    storm = code in STORM_CODES
    storm_risk_flag = storm or (
        p >= alert_rain_mm_h and prob >= min_precip_prob_pct
    )
    risk_score = min(
        100.0,
        (70.0 if storm else 0.0)
        + min(35.0, p * 6.0)
        + min(25.0, prob * 0.25),
    )
    return storm_risk_flag, risk_score


def aggregate_forecast_risk(
    hourly: dict,
    alert_rain_mm_h: float,
    min_precip_prob_pct: int,
) -> tuple[float, int]:
    """
    Returns (max_risk_score, count of hours with storm_risk_flag True).
    """
    h = hourly or {}
    times = h.get("time") or []
    if not times:
        return 0.0, 0

    precip_s = h.get("precipitation") or []
    prob_s = h.get("precipitation_probability") or []
    code_s = h.get("weathercode") or []

    max_score = 0.0
    alert_hours = 0
    for i in range(len(times)):
        precip = precip_s[i] if i < len(precip_s) else None
        prob = prob_s[i] if i < len(prob_s) else None
        wc = code_s[i] if i < len(code_s) else None
        flag, score = hourly_risk(
            float(precip) if precip is not None else None,
            int(prob) if prob is not None else None,
            int(wc) if wc is not None else None,
            alert_rain_mm_h,
            min_precip_prob_pct,
        )
        max_score = max(max_score, score)
        if flag:
            alert_hours += 1
    return max_score, alert_hours
