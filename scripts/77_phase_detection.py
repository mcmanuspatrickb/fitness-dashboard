from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from report_context import load_report_context


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
STATE_DIR = PROJECT_ROOT / "coaching_state"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = STATE_DIR / "phase_config.json"
OUT_JSON = REPORTS_DIR / "current_phase.json"
OUT_TXT = REPORTS_DIR / "phase_detection.txt"
VALID_PHASES = {"cut", "maintenance", "lean_gain"}


def _load_config() -> dict[str, Any]:
    defaults = {
        "mode": "cut",
        "auto_transition": False,
        "target_weight_kg": None,
        "target_body_fat_pct": None,
        "maintenance_band_kcal": 100,
        "lean_gain_surplus_kcal": 150,
    }
    if not CONFIG_PATH.exists():
        return defaults
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    defaults.update(data if isinstance(data, dict) else {})
    if str(defaults.get("mode", "cut")).lower() not in VALID_PHASES:
        defaults["mode"] = "cut"
    defaults["mode"] = str(defaults["mode"]).lower()
    return defaults


def _num(value, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def main() -> None:
    config = _load_config()
    context = load_report_context()
    weekly = context.get("weekly", {})
    trend = context.get("trend_4w", {})
    end_date = context.get("analysis_end_date")

    if end_date is None:
        raise RuntimeError("No complete analysis date available for phase detection.")

    phase = config["mode"]
    latest_weight = weekly.get("latest_weight")
    recent_weight = weekly.get("recent_weight")
    recent_fat = weekly.get("recent_fat")
    weight_delta_4w = trend.get("weight_delta")
    fat_delta_4w = trend.get("fat_delta")
    lean_delta_4w = trend.get("lean_delta")

    body_fat_pct = None
    if recent_weight not in (None, 0) and recent_fat is not None:
        body_fat_pct = float(recent_fat) / float(recent_weight) * 100.0

    target_weight = config.get("target_weight_kg")
    target_bf = config.get("target_body_fat_pct")
    target_reached = False
    target_reasons: list[str] = []
    if target_weight is not None and latest_weight is not None and float(latest_weight) <= float(target_weight):
        target_reached = True
        target_reasons.append("configured target weight has been reached")
    if target_bf is not None and body_fat_pct is not None and body_fat_pct <= float(target_bf):
        target_reached = True
        target_reasons.append("configured target body-fat percentage has been reached")

    suggestion = f"continue {phase}"
    reasons: list[str] = []
    if phase == "cut":
        if target_reached:
            suggestion = "review transition to maintenance"
            reasons.extend(target_reasons)
        elif fat_delta_4w is not None and float(fat_delta_4w) < -0.30:
            suggestion = "continue cut"
            reasons.append("four-week fat mass is still declining")
        elif weight_delta_4w is not None and abs(float(weight_delta_4w)) < 0.30:
            suggestion = "review cut setup"
            reasons.append("four-week scale trend is close to flat")
        else:
            reasons.append("no configured end-point has been reached")
    elif phase == "maintenance":
        if weight_delta_4w is not None and abs(float(weight_delta_4w)) <= 0.75:
            suggestion = "continue maintenance"
            reasons.append("four-week body-weight trend is broadly stable")
        else:
            suggestion = "review maintenance intake"
            reasons.append("four-week body-weight drift is outside the maintenance watch band")
    elif phase == "lean_gain":
        if weight_delta_4w is not None and float(weight_delta_4w) < -0.50:
            suggestion = "review lean-gain intake"
            reasons.append("body weight is still trending down")
        else:
            suggestion = "continue lean gain"
            reasons.append("no strong signal requires a phase change")

    payload = {
        "analysis_end_date": str(end_date),
        "current_phase": phase,
        "auto_transition": bool(config.get("auto_transition", False)),
        "suggestion": suggestion,
        "reasons": reasons,
        "target_weight_kg": target_weight,
        "target_body_fat_pct": target_bf,
        "latest_weight_kg": latest_weight,
        "estimated_recent_body_fat_pct": body_fat_pct,
        "weight_delta_4w_kg": weight_delta_4w,
        "fat_delta_4w_kg": fat_delta_4w,
        "lean_delta_4w_kg": lean_delta_4w,
        "maintenance_band_kcal": config.get("maintenance_band_kcal", 100),
        "lean_gain_surplus_kcal": config.get("lean_gain_surplus_kcal", 150),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "Coaching Phase",
        "==============",
        "",
        f"analysis through: {end_date}",
        f"current phase: {phase}",
        f"automatic phase switching: {'enabled' if payload['auto_transition'] else 'disabled'}",
        f"suggestion: {suggestion}",
        "",
        "Current Context",
        "---------------",
        f"latest weight: {_num(latest_weight)} kg",
        f"estimated recent body fat: {_num(body_fat_pct, 1)}%",
        f"4-week weight change: {_num(weight_delta_4w)} kg",
        f"4-week fat-mass change: {_num(fat_delta_4w)} kg",
        f"4-week BIA lean-mass change: {_num(lean_delta_4w)} kg",
        "",
        "Why",
        "---",
    ]
    lines.extend(f"- {reason}" for reason in reasons)
    lines.extend([
        "",
        "Method Note",
        "-----------",
        "The configured phase controls calorie logic. The detector may suggest reviewing the phase, but it does not automatically switch phases unless that behavior is explicitly enabled later.",
        "Body-fat percentage here is derived from current BIA fat mass and body weight, so it should be treated as a trend estimate rather than an exact endpoint measurement.",
    ])
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"Saved: {OUT_JSON}")
    print(f"Saved: {OUT_TXT}")


if __name__ == "__main__":
    main()
