from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import psycopg

from report_context import load_report_context


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = REPORTS_DIR / "canonical_coaching_snapshot.json"
OUT_TXT = REPORTS_DIR / "canonical_coaching_snapshot.txt"

PHASE_JSON = REPORTS_DIR / "current_phase.json"
GUARDRAIL_JSON = REPORTS_DIR / "cut_stress_guardrail.json"
CALORIE_JSON = REPORTS_DIR / "adaptive_calorie_recommendation.json"
PERSONAL_BLOCKS = REPORTS_DIR / "personal_response_blocks.csv"
FEEDBACK_HISTORY = PROJECT_ROOT / "coaching_state" / "adaptive_coaching_history.csv"

ENERGY_KCAL_PER_KG = 7700.0
PROTEIN_LOW_PER_KG_LEAN = 1.8
PROTEIN_HIGH_PER_KG_LEAN = 2.2
PERSONAL_ADJUSTMENT_MIN_BLOCKS = 12

EXCLUDED_SET_TYPES = {
    "warmup", "warm-up", "warm_up", "warm up",
    "dropset", "drop-set", "drop_set", "drop set",
}

# Primary-muscle mapping only. Compound exercises are intentionally counted once
# so this remains a transparent training-dose signal rather than pretending to
# know fractional stimulus for every secondary muscle.
MUSCLE_PATTERNS: list[tuple[str, str]] = [
    ("Shoulders", r"\b(overhead|military|shoulder press|lateral raise|rear delt|face pull)\b"),
    ("Chest", r"\b(bench press|chest press|pec deck|chest fly|cable fly|push[ -]?up)\b"),
    ("Back", r"\b(row|pulldown|pull[ -]?up|chin[ -]?up|lat pull)\b"),
    ("Quads", r"\b(back squat|barbell squat|front squat|leg press|leg extension|lunge|split squat|hack squat)\b"),
    ("Posterior chain", r"\b(deadlift|romanian|rdl|leg curl|hamstring|hip thrust|glute bridge)\b"),
    ("Biceps", r"\b(biceps|curl)\b"),
    ("Triceps", r"\b(triceps|pushdown|skull crusher|extension)\b"),
    ("Calves", r"\b(calf|calves)\b"),
    ("Core", r"\b(crunch|plank|ab wheel|abdominal|hanging leg raise|sit[ -]?up)\b"),
]


def _load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = default or {}
    if not path.exists():
        return fallback
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else fallback
    except Exception:
        return fallback


def _float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round25(value: float | None) -> float | None:
    if value is None:
        return None
    return float(round(value / 25.0) * 25.0)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if value is pd.NA or (not isinstance(value, (str, bytes)) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def _energy_frame(end_date: date, days: int) -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        frame = con.execute(
            """
            SELECT d.date, b.weight_kg, n.calories
            FROM analytics.daily_metrics d
            LEFT JOIN clean.body_composition b ON d.date=b.date
            LEFT JOIN clean.nutrition_daily n ON d.date=n.date
            WHERE d.date BETWEEN (?::DATE - (? - 1) * INTERVAL 1 DAY) AND ?::DATE
            ORDER BY d.date
            """,
            [end_date, days, end_date],
        ).fetchdf()
    finally:
        con.close()
    return frame


def _energy_estimate(frame: pd.DataFrame, recent_weight: float | None, days: int) -> dict[str, Any]:
    result = {
        "days": days, "estimated_tdee": None, "estimated_deficit": None,
        "weight_loss_pct_week": None, "avg_calories": None,
        "calorie_days": 0, "weight_days": 0, "coverage": "LOW",
    }
    if frame.empty:
        return result
    local = frame.copy()
    local["date"] = pd.to_datetime(local["date"], errors="coerce")
    local["weight_kg"] = pd.to_numeric(local["weight_kg"], errors="coerce")
    local["calories"] = pd.to_numeric(local["calories"], errors="coerce")
    calories = local["calories"].dropna()
    weights = local[["date", "weight_kg"]].dropna().sort_values("date")
    result["calorie_days"] = int(len(calories))
    result["weight_days"] = int(len(weights))
    result["avg_calories"] = float(calories.mean()) if not calories.empty else None

    min_cal = 21 if days <= 28 else 31
    min_weight = 12 if days <= 28 else 18
    high_cal = 25 if days <= 28 else 37
    high_weight = 20 if days <= 28 else 28
    if len(calories) >= high_cal and len(weights) >= high_weight:
        result["coverage"] = "HIGH"
    elif len(calories) >= min_cal and len(weights) >= min_weight:
        result["coverage"] = "MEDIUM"
    if len(calories) < min_cal or len(weights) < min_weight:
        return result

    x = (weights["date"] - weights["date"].min()).dt.total_seconds() / 86400.0
    y = weights["weight_kg"].astype(float)
    xc = x - x.mean()
    denominator = float((xc ** 2).sum())
    if denominator <= 0:
        return result
    slope = float((xc * (y - y.mean())).sum() / denominator)
    avg_calories = float(result["avg_calories"])
    tdee = avg_calories - slope * ENERGY_KCAL_PER_KG
    if not 1200 <= tdee <= 5000:
        return result
    result["estimated_tdee"] = tdee
    result["estimated_deficit"] = tdee - avg_calories
    if recent_weight is not None and recent_weight > 0:
        result["weight_loss_pct_week"] = -slope * 7.0 / recent_weight * 100.0
    return result


def _energy_consensus(end_date: date, recent_weight: float | None) -> dict[str, Any]:
    e28 = _energy_estimate(_energy_frame(end_date, 28), recent_weight, 28)
    e42 = _energy_estimate(_energy_frame(end_date, 42), recent_weight, 42)
    estimates = [
        value for value in [e28.get("estimated_tdee"), e42.get("estimated_tdee")]
        if value is not None
    ]
    planning = None
    stability = "UNAVAILABLE"
    low = high = None
    difference = None
    if len(estimates) == 2:
        difference = abs(estimates[0] - estimates[1])
        planning = sum(estimates) / 2.0
        if difference <= 150:
            stability = "STABLE"
        elif difference <= 300:
            stability = "WATCH"
        else:
            stability = "UNSTABLE"
        low = min(estimates) - 100.0
        high = max(estimates) + 100.0
    elif len(estimates) == 1:
        planning = estimates[0]
        stability = "SINGLE_WINDOW"
        low, high = planning - 175.0, planning + 175.0

    return {
        "window_28": e28,
        "window_42": e42,
        "planning_tdee": _round25(planning),
        "planning_range_low": _round25(low),
        "planning_range_high": _round25(high),
        "window_difference": difference,
        "stability": stability,
    }


def _normalize_set_type(value: Any) -> str:
    return str(value or "normal").strip().lower().replace("_", " ")


def _muscle_group(title: Any) -> str:
    text = str(title or "").strip().lower()
    for group, pattern in MUSCLE_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return group
    return "Other / unmapped"


def _training_dose(end_date: date) -> dict[str, Any]:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        frame = con.execute(
            """
            SELECT CAST(w.start_time AS DATE) AS date,
                   s.exercise_title, s.set_type, s.weight_kg, s.reps, s.rpe
            FROM raw.hevy_sets s
            JOIN raw.hevy_workouts w ON s.workout_id=w.workout_id
            WHERE CAST(w.start_time AS DATE) BETWEEN (?::DATE - INTERVAL 27 DAY) AND ?::DATE
            ORDER BY w.start_time
            """,
            [end_date, end_date],
        ).fetchdf()
    finally:
        con.close()
    if frame.empty:
        return {"groups": [], "unmapped_working_sets_28d": 0, "rpe_coverage_pct": None}

    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    frame["reps"] = pd.to_numeric(frame["reps"], errors="coerce")
    frame["weight_kg"] = pd.to_numeric(frame["weight_kg"], errors="coerce")
    frame["rpe"] = pd.to_numeric(frame["rpe"], errors="coerce")
    frame["set_type_norm"] = frame["set_type"].map(_normalize_set_type)
    frame["working"] = (~frame["set_type_norm"].isin(EXCLUDED_SET_TYPES)) & frame["reps"].fillna(0).gt(0)
    work = frame[frame["working"]].copy()
    if work.empty:
        return {"groups": [], "unmapped_working_sets_28d": 0, "rpe_coverage_pct": None}
    work["muscle_group"] = work["exercise_title"].map(_muscle_group)
    work["hard_set"] = work["rpe"].ge(7.5)
    start7 = end_date - timedelta(days=6)
    rows = []
    for group in [g for g, _ in MUSCLE_PATTERNS] + ["Other / unmapped"]:
        sub28 = work[work["muscle_group"] == group]
        if sub28.empty:
            continue
        sub7 = sub28[sub28["date"].between(start7, end_date)]
        rpe_values = sub28["rpe"].dropna()
        rows.append({
            "muscle_group": group,
            "working_sets_7d": int(len(sub7)),
            "working_sets_28d": int(len(sub28)),
            "hard_sets_7d": int(sub7["hard_set"].sum()),
            "hard_sets_28d": int(sub28["hard_set"].sum()),
            "avg_rpe_28d": None if rpe_values.empty else float(rpe_values.mean()),
        })
    rpe_coverage = float(work["rpe"].notna().mean() * 100.0) if len(work) else None
    unmapped = int((work["muscle_group"] == "Other / unmapped").sum())
    return {
        "groups": rows,
        "unmapped_working_sets_28d": unmapped,
        "rpe_coverage_pct": rpe_coverage,
        "method": "Primary-muscle working-set count; compounds are counted once. Hard sets require logged RPE >=7.5.",
    }


def _median_mad(values: pd.Series) -> tuple[float | None, float | None]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None, None
    median = float(numeric.median())
    mad = float((numeric - median).abs().median())
    return median, mad


def _recovery_baselines(context: dict[str, Any]) -> dict[str, Any]:
    trailing = context.get("trailing_28", pd.DataFrame()).copy()
    end_date = context.get("analysis_end_date")
    result = {
        "rhr_baseline": None, "rhr_recent": None, "rhr_state": "INSUFFICIENT_DATA",
        "hrv_baseline": None, "hrv_recent": None, "hrv_state": "INSUFFICIENT_DATA",
    }
    if trailing.empty or end_date is None:
        return result
    trailing["date"] = pd.to_datetime(trailing["date"], errors="coerce").dt.date
    baseline_end = end_date - timedelta(days=7)
    baseline = trailing[trailing["date"] <= baseline_end]
    recent = trailing[trailing["date"].between(end_date - timedelta(days=6), end_date)]

    rhr_base, rhr_mad = _median_mad(baseline["resting_hr"])
    rhr_recent, _ = _median_mad(recent["resting_hr"])
    hrv_base, hrv_mad = _median_mad(baseline["hrv"])
    hrv_recent, _ = _median_mad(recent["hrv"])
    result.update({"rhr_baseline": rhr_base, "rhr_recent": rhr_recent, "hrv_baseline": hrv_base, "hrv_recent": hrv_recent})

    if rhr_base is not None and rhr_recent is not None:
        threshold = max(2.0, 1.5 * (rhr_mad or 0.0))
        result["rhr_threshold_bpm"] = threshold
        result["rhr_state"] = "ELEVATED" if rhr_recent > rhr_base + threshold else "NORMAL_FOR_USER"
    if hrv_base is not None and hrv_recent is not None:
        threshold = max(2.0, 1.5 * (hrv_mad or 0.0))
        result["hrv_threshold_ms"] = threshold
        result["hrv_state"] = "LOW_FOR_USER" if hrv_recent < hrv_base - threshold else "NORMAL_FOR_USER"
    return result


def _adherence(context: dict[str, Any]) -> dict[str, Any]:
    current = context.get("current", pd.DataFrame()).copy()
    weekly = context.get("weekly", {})
    lean = _float(weekly.get("recent_lean"))
    protein_min = lean * PROTEIN_LOW_PER_KG_LEAN if lean else None
    protein_high = lean * PROTEIN_HIGH_PER_KG_LEAN if lean else None
    result = {
        "protein_target_min_g": protein_min,
        "protein_target_high_g": protein_high,
        "protein_days_met": 0, "protein_days_logged": 0, "protein_hit_rate_pct": None,
        "sleep_7h_days": 0, "sleep_days_logged": 0, "sleep_hit_rate_pct": None,
        "steps_7000_days": 0, "steps_8000_days": 0, "steps_days_logged": 0,
        "workouts_7d": _float(weekly.get("recent_workouts")) or 0.0,
    }
    if current.empty:
        return result
    protein = pd.to_numeric(current.get("protein_g"), errors="coerce").dropna()
    sleep = pd.to_numeric(current.get("sleep_hours"), errors="coerce").dropna()
    steps = pd.to_numeric(current.get("steps"), errors="coerce").dropna()
    result["protein_days_logged"] = int(len(protein))
    if protein_min is not None and len(protein):
        result["protein_days_met"] = int((protein >= protein_min).sum())
        result["protein_hit_rate_pct"] = float((protein >= protein_min).mean() * 100.0)
    result["sleep_days_logged"] = int(len(sleep))
    if len(sleep):
        result["sleep_7h_days"] = int((sleep >= 7.0).sum())
        result["sleep_hit_rate_pct"] = float((sleep >= 7.0).mean() * 100.0)
    result["steps_days_logged"] = int(len(steps))
    if len(steps):
        result["steps_7000_days"] = int((steps >= 7000).sum())
        result["steps_8000_days"] = int((steps >= 8000).sum())
    return result


def _personal_evidence() -> dict[str, Any]:
    result = {"comparable_blocks": 0, "evidence_tier": "BUILDING", "adjustment_minimum": PERSONAL_ADJUSTMENT_MIN_BLOCKS}
    if not PERSONAL_BLOCKS.exists():
        return result
    try:
        blocks = pd.read_csv(PERSONAL_BLOCKS)
    except Exception:
        return result
    if blocks.empty or "workouts" not in blocks.columns:
        return result
    workouts = pd.to_numeric(blocks["workouts"], errors="coerce").fillna(0)
    mask = workouts >= 2
    if "fasting_days" in blocks.columns:
        mask &= pd.to_numeric(blocks["fasting_days"], errors="coerce").fillna(0).eq(0)
    n = int(mask.sum())
    tier = "BUILDING" if n < 8 else "PRELIMINARY" if n < 12 else "DEVELOPING" if n < 20 else "MATURE"
    result.update({"comparable_blocks": n, "evidence_tier": tier, "additional_to_adjustment": max(0, PERSONAL_ADJUSTMENT_MIN_BLOCKS - n)})
    return result


def _latest_feedback() -> dict[str, Any]:
    payload = _load_json(CALORIE_JSON, {})
    result = {
        "decision_date": payload.get("decision_date"),
        "feedback_evidence": payload.get("feedback_evidence", {}),
        "history_events": 0,
        "mature_28d_events": 0,
    }
    if FEEDBACK_HISTORY.exists():
        try:
            history = pd.read_csv(FEEDBACK_HISTORY)
            result["history_events"] = int(len(history))
            if "outcome28_status" in history.columns:
                result["mature_28d_events"] = int(history["outcome28_status"].astype(str).isin(["HELPFUL", "NEUTRAL", "ADVERSE"]).sum())
        except Exception:
            pass
    return result


def _persist(snapshot: dict[str, Any]) -> str:
    url = os.getenv("WITHINGS_DATABASE_URL", "").strip()
    if not url:
        return "skipped: WITHINGS_DATABASE_URL not available"
    payload = json.dumps(_json_safe(snapshot), ensure_ascii=False)
    with psycopg.connect(url) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS coaching_snapshots (
                analysis_date DATE PRIMARY KEY,
                generated_at TIMESTAMPTZ NOT NULL,
                phase TEXT,
                fat_loss_state TEXT,
                muscle_preservation_state TEXT,
                recovery_state TEXT,
                training_state TEXT,
                data_confidence TEXT,
                snapshot_json JSONB NOT NULL
            )
            """
        )
        con.execute(
            """
            INSERT INTO coaching_snapshots (
                analysis_date, generated_at, phase, fat_loss_state,
                muscle_preservation_state, recovery_state, training_state,
                data_confidence, snapshot_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (analysis_date) DO UPDATE SET
                generated_at=EXCLUDED.generated_at,
                phase=EXCLUDED.phase,
                fat_loss_state=EXCLUDED.fat_loss_state,
                muscle_preservation_state=EXCLUDED.muscle_preservation_state,
                recovery_state=EXCLUDED.recovery_state,
                training_state=EXCLUDED.training_state,
                data_confidence=EXCLUDED.data_confidence,
                snapshot_json=EXCLUDED.snapshot_json
            """,
            (
                snapshot["analysis_date"], snapshot["generated_at"], snapshot["phase"],
                snapshot["states"]["fat_loss"], snapshot["states"]["muscle_preservation"],
                snapshot["states"]["recovery"], snapshot["states"]["training"],
                snapshot["data_quality"]["confidence"], payload,
            ),
        )
        con.commit()
    return "persisted"


def main() -> None:
    context = load_report_context()
    end_date = context.get("analysis_end_date")
    if end_date is None:
        raise RuntimeError("No complete analysis date available for canonical coaching snapshot.")

    weekly = context.get("weekly", {})
    trend = context.get("trend_4w", {})
    strength_lifts = context.get("strength_4w", [])
    performance = context.get("performance", {})
    coverage = context.get("coverage", {})
    phase_info = _load_json(PHASE_JSON, {"current_phase": "cut", "suggestion": "n/a"})
    guardrail = _load_json(GUARDRAIL_JSON, {"status": "STABLE", "concerns": [], "reassuring_signals": []})
    calorie = _load_json(CALORIE_JSON, {})

    recent_weight = _float(weekly.get("recent_weight"))
    energy = _energy_consensus(end_date, recent_weight)
    adherence = _adherence(context)
    training_dose = _training_dose(end_date)
    recovery = _recovery_baselines(context)
    personal = _personal_evidence()
    feedback = _latest_feedback()

    fat_delta = _float(trend.get("fat_delta"))
    lean_delta = _float(trend.get("lean_delta"))
    pace = _float(energy.get("window_28", {}).get("weight_loss_pct_week"))
    strength_up = sum(1 for item in strength_lifts if item.get("direction") == "up")
    strength_flat = sum(1 for item in strength_lifts if item.get("direction") == "flat")
    strength_down = sum(1 for item in strength_lifts if item.get("direction") == "down")
    waist_change = _float(performance.get("waist_change_cm"))
    grip_count = int(performance.get("grip_measurement_count", 0) or 0)
    grip_trend = _float(performance.get("grip_trend_pct"))

    if fat_delta is not None and fat_delta < -0.30:
        fat_state = "PROGRESSING"
    elif pace is not None and pace > 0.15:
        fat_state = "PROGRESSING_SLOWLY"
    else:
        fat_state = "NOT_CONFIRMED"

    concern_evidence: list[str] = []
    reassuring_evidence: list[str] = []
    if lean_delta is not None and lean_delta <= -0.75:
        concern_evidence.append(f"BIA lean-mass trend is {lean_delta:+.2f} kg across the comparison window")
    if adherence.get("protein_hit_rate_pct") is not None and adherence["protein_hit_rate_pct"] < 60:
        concern_evidence.append(f"protein target was reached on only {adherence['protein_days_met']}/{adherence['protein_days_logged']} logged days")
    if adherence.get("sleep_hit_rate_pct") is not None and adherence["sleep_hit_rate_pct"] < 50:
        concern_evidence.append(f"7+ hours of sleep occurred on {adherence['sleep_7h_days']}/{adherence['sleep_days_logged']} logged nights")
    if adherence.get("workouts_7d", 0) < 2:
        concern_evidence.append("fewer than two resistance sessions were completed in the latest 7-day window")
    if grip_count >= 4 and grip_trend is not None and grip_trend <= -8:
        concern_evidence.append(f"grip trend is down {abs(grip_trend):.1f}%")

    if strength_down == 0 and (strength_up + strength_flat) >= 2:
        reassuring_evidence.append(f"all {strength_up + strength_flat} comparable strength trends are preserved or improving")
    if fat_delta is not None and fat_delta < -0.30:
        reassuring_evidence.append(f"BIA fat-mass trend is {fat_delta:+.2f} kg")
    if waist_change is not None and waist_change < -0.5:
        reassuring_evidence.append(f"waist is down {abs(waist_change):.1f} cm from the prior measurement")
    if pace is not None and 0.25 <= pace <= 0.75:
        reassuring_evidence.append(f"weight-loss pace is moderate at about {pace:.2f}%/week")
    if grip_count >= 4 and grip_trend is not None and grip_trend >= -3:
        reassuring_evidence.append("grip is broadly stable")

    if strength_down >= 2 or (lean_delta is not None and lean_delta <= -0.75 and grip_count >= 4 and grip_trend is not None and grip_trend <= -8):
        muscle_state = "CONCERN"
    elif concern_evidence:
        muscle_state = "WATCH"
    else:
        muscle_state = "STABLE"

    workouts7 = adherence.get("workouts_7d", 0)
    touched_groups = sum(1 for row in training_dose.get("groups", []) if row.get("working_sets_7d", 0) > 0 and row.get("muscle_group") != "Other / unmapped")
    if workouts7 >= 2 and touched_groups >= 4:
        training_state = "ON_TARGET"
    elif workouts7 >= 2:
        training_state = "SESSIONS_MET_PARTIAL_COVERAGE"
    else:
        training_state = "BELOW_TARGET"

    recovery_state = str(guardrail.get("status", "STABLE"))
    decision = {
        "action": calorie.get("action", "HOLD"),
        "calorie_adjustment": calorie.get("final_calorie_adjustment", calorie.get("original_calorie_adjustment", 0)),
        "target_intake": calorie.get("target_intake"),
        "target_deficit": calorie.get("target_deficit"),
    }

    priorities: list[str] = []
    if adherence.get("protein_hit_rate_pct") is not None and adherence["protein_hit_rate_pct"] < 80:
        priorities.append(f"Protein: reach at least {adherence['protein_target_min_g']:.0f} g on most days")
    if workouts7 < 2:
        priorities.append("Resistance training: complete both planned sessions")
    if adherence.get("sleep_hit_rate_pct") is not None and adherence["sleep_hit_rate_pct"] < 70:
        priorities.append("Sleep: increase the number of nights reaching 7+ hours")
    if adherence.get("steps_days_logged", 0) and adherence.get("steps_7000_days", 0) < 4:
        priorities.append("Movement: treat ~7,000 steps as the floor and ~8,000+ as the preferred target when recovery allows")
    if not priorities:
        priorities.append("Maintain the current plan and keep data collection consistent")

    interpretation = [
        f"Fat-loss state is {fat_state.lower().replace('_', ' ')}; muscle-preservation state is {muscle_state.lower()}.",
    ]
    if reassuring_evidence:
        interpretation.append("Reassuring evidence: " + "; ".join(reassuring_evidence[:4]) + ".")
    if concern_evidence:
        interpretation.append("Watch evidence: " + "; ".join(concern_evidence[:4]) + ".")
    if energy.get("planning_tdee") is not None:
        lo, hi = energy.get("planning_range_low"), energy.get("planning_range_high")
        interpretation.append(
            f"Planning maintenance is about {energy['planning_tdee']:.0f} kcal/day"
            + (f" with a working range of roughly {lo:.0f}-{hi:.0f} kcal/day" if lo is not None and hi is not None else "")
            + f"; 28/42-day agreement is {str(energy.get('stability')).lower()}."
        )
    if grip_count < 4:
        interpretation.append(f"Grip has {grip_count} standardized measurement(s), so it is recorded but not yet used as a trend signal.")
    elif grip_trend is not None:
        interpretation.append(f"Grip short-term trend is {grip_trend:+.1f}% and is included as an independent functional cross-check.")

    snapshot = {
        "schema_version": 1,
        "analysis_date": str(end_date),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phase": str(phase_info.get("current_phase", "cut")),
        "phase_suggestion": phase_info.get("suggestion"),
        "data_quality": {
            "confidence": coverage.get("confidence", "LOW"),
            "checks_passed": coverage.get("checks_passed"),
            "checks_total": coverage.get("checks_total"),
        },
        "states": {
            "fat_loss": fat_state,
            "muscle_preservation": muscle_state,
            "recovery": recovery_state,
            "training": training_state,
        },
        "body": {
            "recent_weight_kg": recent_weight,
            "weight_change_window_kg": _float(trend.get("weight_delta")),
            "fat_change_window_kg": fat_delta,
            "bia_lean_change_window_kg": lean_delta,
            "loss_rate_pct_week": pace,
            "latest_waist_cm": _float(performance.get("latest_waist_cm")),
            "waist_change_cm": waist_change,
            "latest_waist_date": performance.get("latest_waist_date"),
        },
        "energy": energy,
        "nutrition": {
            "calories_7d": _float(weekly.get("recent_calories")),
            "protein_7d_g": _float(weekly.get("recent_protein")),
            "protein_target_low_g": adherence.get("protein_target_min_g"),
            "protein_target_high_g": adherence.get("protein_target_high_g"),
        },
        "adherence": adherence,
        "strength": {
            "up": strength_up, "flat": strength_flat, "down": strength_down,
            "lifts": strength_lifts,
        },
        "training_dose": training_dose,
        "recovery": recovery,
        "performance": {
            "grip_measurement_count": grip_count,
            "latest_grip_kg": _float(performance.get("latest_grip_overall_kg")),
            "latest_grip_left_kg": _float(performance.get("latest_grip_left_kg")),
            "latest_grip_right_kg": _float(performance.get("latest_grip_right_kg")),
            "grip_asymmetry_pct": _float(performance.get("latest_grip_asymmetry_pct")),
            "grip_trend_pct": grip_trend,
        },
        "guardrail": guardrail,
        "decision": decision,
        "personal_response": personal,
        "adaptive_feedback": feedback,
        "muscle_preservation_evidence": {
            "watch": concern_evidence,
            "reassuring": reassuring_evidence,
        },
        "priorities": priorities[:4],
        "interpretation": interpretation,
        "notes": [
            "BIA fat-free mass is supporting evidence, not a direct measurement of contractile muscle.",
            "The canonical snapshot is the authoritative coaching interpretation; dashboard charts remain exploratory views of the underlying data.",
            "Personal-response associations are not allowed to influence calorie adjustments until at least 12 comparable training-active normal-diet blocks exist.",
        ],
    }
    snapshot = _json_safe(snapshot)
    OUT_JSON.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "Canonical Coaching Snapshot", "===========================", "",
        f"analysis date: {snapshot['analysis_date']}",
        f"phase: {snapshot['phase']}",
        f"fat loss: {snapshot['states']['fat_loss']}",
        f"muscle preservation: {snapshot['states']['muscle_preservation']}",
        f"recovery: {snapshot['states']['recovery']}",
        f"training: {snapshot['states']['training']}", "",
        "Decision", "--------",
        f"action: {decision['action']}",
        f"calorie adjustment: {decision['calorie_adjustment']}",
        f"target intake: {decision['target_intake']}", "",
        "Priorities", "----------",
    ]
    lines.extend(f"- {item}" for item in snapshot["priorities"])
    lines.extend(["", "Interpretation", "--------------"])
    lines.extend(f"- {item}" for item in snapshot["interpretation"])
    lines.extend(["", "Training Dose", "-------------"])
    for row in snapshot["training_dose"]["groups"]:
        lines.append(f"- {row['muscle_group']}: {row['working_sets_7d']} working sets / 7d; {row['working_sets_28d']} / 28d; hard sets 7d={row['hard_sets_7d']}")
    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")

    persist_status = _persist(snapshot)
    print("\n".join(lines))
    print(f"Saved: {OUT_JSON}")
    print(f"Saved: {OUT_TXT}")
    print(f"Persistent snapshot: {persist_status}")


if __name__ == "__main__":
    main()
