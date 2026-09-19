from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from report_context import load_report_context


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
OUT_JSON = REPORTS_DIR / "cut_stress_guardrail.json"
OUT_TXT = REPORTS_DIR / "cut_stress_guardrail.txt"
PHASE_JSON = REPORTS_DIR / "current_phase.json"


def _load_phase() -> str:
    if not PHASE_JSON.exists():
        return "cut"
    try:
        return str(json.loads(PHASE_JSON.read_text(encoding="utf-8")).get("current_phase", "cut"))
    except Exception:
        return "cut"


def _num(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def _strength_counts(items: list[dict[str, Any]]) -> tuple[int, int, int]:
    up = sum(1 for item in items if item.get("direction") == "up")
    flat = sum(1 for item in items if item.get("direction") == "flat")
    down = sum(1 for item in items if item.get("direction") == "down")
    return up, flat, down


def main() -> None:
    context = load_report_context()
    weekly = context.get("weekly", {})
    trend = context.get("trend_4w", {})
    performance = context.get("performance", {})
    strength = context.get("strength_4w", [])
    end_date = context.get("analysis_end_date")
    phase = _load_phase()

    if end_date is None:
        raise RuntimeError("No complete analysis date available for recovery guardrail.")

    up, flat, down = _strength_counts(strength)
    concerns: list[str] = []
    reassuring: list[str] = []

    sleep = weekly.get("recent_sleep")
    sleep_delta = weekly.get("sleep_delta")
    rhr_delta = weekly.get("rhr_delta")
    hrv_delta = weekly.get("hrv_delta")
    lean_delta_4w = trend.get("lean_delta")
    fat_delta_4w = trend.get("fat_delta")
    weight_delta_4w = trend.get("weight_delta")
    avg_calories_28 = trend.get("avg_calories")
    recent_calories = weekly.get("recent_calories")
    grip_trend_pct = performance.get("grip_trend_pct")
    grip_count = performance.get("grip_measurement_count", 0)
    waist_change = performance.get("waist_change_cm")

    if sleep is not None and float(sleep) < 6.25:
        concerns.append(f"sleep is low at about {float(sleep):.1f} h/night")
    elif sleep_delta is not None and float(sleep_delta) <= -0.75:
        concerns.append(f"sleep fell by {abs(float(sleep_delta)):.1f} h/night versus the prior week")
    elif sleep is not None and float(sleep) >= 7.0:
        reassuring.append("sleep is at or above 7 h/night")

    if rhr_delta is not None and float(rhr_delta) >= 3.0:
        concerns.append(f"resting HR is up {float(rhr_delta):.1f} bpm versus the prior week")
    elif rhr_delta is not None and float(rhr_delta) <= 0:
        reassuring.append("resting HR is not rising")

    if hrv_delta is not None and float(hrv_delta) <= -3.0:
        concerns.append(f"HRV is down {abs(float(hrv_delta)):.1f} ms versus the prior week")
    elif hrv_delta is not None and float(hrv_delta) >= 0:
        reassuring.append("HRV is stable or improving")

    if down >= 2:
        concerns.append(f"{down} comparable four-week strength trends are down")
    elif down == 0 and (up + flat) >= 2:
        reassuring.append(f"strength is preserved across {up + flat} comparable lifts")

    if lean_delta_4w is not None and float(lean_delta_4w) <= -0.75:
        concerns.append(f"four-week BIA lean-mass trend is {float(lean_delta_4w):+.2f} kg")

    if phase == "cut" and weight_delta_4w is not None and float(weight_delta_4w) < -3.0:
        concerns.append("four-week scale loss is unusually aggressive")

    if (
        phase == "cut"
        and recent_calories is not None
        and avg_calories_28 is not None
        and float(avg_calories_28) > 0
        and float(recent_calories) / float(avg_calories_28) <= 0.85
    ):
        concerns.append("the current week is at least 15% below the 28-day calorie average")

    if grip_count >= 4 and grip_trend_pct is not None:
        if float(grip_trend_pct) <= -8.0:
            concerns.append(f"grip strength trend is down about {abs(float(grip_trend_pct)):.1f}%")
        elif float(grip_trend_pct) >= -3.0:
            reassuring.append("grip strength is broadly stable")

    if waist_change is not None and float(waist_change) < -0.5:
        reassuring.append(f"waist is down {abs(float(waist_change)):.1f} cm from the prior measurement")
    if fat_delta_4w is not None and float(fat_delta_4w) < -0.30:
        reassuring.append("four-week fat mass is declining")

    severe = any(
        phrase in " ".join(concerns).lower()
        for phrase in ["strength trends are down", "resting hr is up", "hrv is down"]
    )
    if len(concerns) >= 3 or (len(concerns) >= 2 and severe):
        status = "RECOVERY_CONCERN"
        interpretation = "Several independent signals are moving against recovery or muscle preservation. Do not deepen the deficit this week."
    elif concerns:
        status = "WATCH"
        interpretation = "At least one recovery or preservation signal deserves attention, but the evidence is not broad enough to call the cut unstable."
    else:
        status = "STABLE"
        interpretation = "No multi-signal recovery concern is present in the current reporting window."

    payload = {
        "analysis_end_date": str(end_date),
        "phase": phase,
        "status": status,
        "concerns": concerns,
        "reassuring_signals": reassuring,
        "strength_up": up,
        "strength_flat": flat,
        "strength_down": down,
        "grip_measurement_count": grip_count,
        "grip_trend_pct": grip_trend_pct,
        "waist_change_cm": waist_change,
        "interpretation": interpretation,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "Cut Stress / Recovery Guardrail",
        "===============================",
        "",
        f"analysis through: {end_date}",
        f"phase: {phase}",
        f"status: {status}",
        f"interpretation: {interpretation}",
        "",
        "Signals of Concern",
        "------------------",
    ]
    if concerns:
        lines.extend(f"- {item}" for item in concerns)
    else:
        lines.append("- none")
    lines.extend(["", "Reassuring Signals", "------------------"])
    if reassuring:
        lines.extend(f"- {item}" for item in reassuring)
    else:
        lines.append("- none strong enough to list")
    lines.extend([
        "",
        "Performance Markers",
        "-------------------",
        f"grip measurements available: {grip_count}",
        f"grip short-term trend: {_num(grip_trend_pct, 1)}%",
        f"waist change vs prior measurement: {_num(waist_change, 1)} cm",
        "",
        "Method Note",
        "-----------",
        "The guardrail deliberately requires multiple independent signals before escalating concern. One noisy BIA reading, one poor night of sleep, or one weak workout is not enough by itself.",
        "Grip is only used as a trend signal after at least four measurements. Waist is supportive context, not a recovery metric.",
    ])
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"Saved: {OUT_JSON}")
    print(f"Saved: {OUT_TXT}")


if __name__ == "__main__":
    main()
