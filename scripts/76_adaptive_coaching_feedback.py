from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from report_context import load_report_context


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"
REPORTS_DIR = PROJECT_ROOT / "reports"
STATE_DIR = PROJECT_ROOT / "coaching_state"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR.mkdir(parents=True, exist_ok=True)

RECOMMENDATION_PATH = REPORTS_DIR / "adaptive_calorie_recommendation.txt"
RECOMMENDATION_JSON = REPORTS_DIR / "adaptive_calorie_recommendation.json"
FEEDBACK_REPORT = REPORTS_DIR / "adaptive_coaching_feedback.txt"
HISTORY_PATH = STATE_DIR / "adaptive_coaching_history.csv"
STRENGTH_CSV = REPORTS_DIR / "strength_progress_weekly.csv"
PHASE_JSON = REPORTS_DIR / "current_phase.json"

MIN_FEEDBACK_EVENTS = 4
DAMPENED_ADJUSTMENT = 50
EFFECTIVENESS_HORIZON = 28

BASE_COLUMNS = [
    "decision_id", "decision_date", "analysis_end_date", "phase", "action",
    "calorie_adjustment", "target_intake", "estimated_tdee", "target_deficit",
    "target_protein_min", "target_sleep_h", "target_workouts", "target_steps",
    "baseline_calories", "baseline_protein", "baseline_weight", "baseline_fat",
    "baseline_lean", "baseline_sleep", "baseline_rhr", "baseline_hrv",
    "baseline_steps", "baseline_grip_kg", "baseline_waist_cm",
    "baseline_strength_up", "baseline_strength_flat", "baseline_strength_down",
    "decision_reason",
]
OUTCOME_FIELDS = [
    "status", "evaluated_date", "calorie_adherence", "protein_adherence",
    "sleep_adherence", "training_adherence", "steps_adherence",
    "actual_calories", "actual_protein", "actual_sleep", "actual_workouts",
    "actual_steps", "calorie_change", "weight_delta", "fat_delta", "lean_delta",
    "sleep_delta", "rhr_delta", "hrv_delta", "steps_delta", "grip_delta_pct",
    "waist_delta_cm", "strength_up", "strength_flat", "strength_down", "confounded",
]
HISTORY_COLUMNS = BASE_COLUMNS + [
    f"outcome{horizon}_{field}"
    for horizon in (7, 14, 28)
    for field in OUTCOME_FIELDS
] + ["created_at_utc", "updated_at_utc"]


def _num(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def _float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_number(text: str, label: str) -> float | None:
    match = re.search(rf"^{re.escape(label)}:\s*([+-]?\d+(?:\.\d+)?)", text, flags=re.MULTILINE)
    return float(match.group(1)) if match else None


def _parse_recommendation(text: str) -> dict[str, Any]:
    action_match = re.search(r"^Action:\s*(INCREASE|DECREASE|HOLD)\s*$", text, re.MULTILINE)
    adjustment_match = re.search(r"^Calorie adjustment:\s*([+-]?\d+)\s*kcal/day\s*$", text, re.MULTILINE)
    end_match = re.search(r"^Reporting window ends:\s*(\d{4}-\d{2}-\d{2})", text, re.MULTILINE)
    phase_match = re.search(r"^current phase:\s*(\w+)\s*$", text, re.MULTILINE)
    why_match = re.search(r"\nWhy\n---\n(.*?)(?=\n\n(?:Adaptive Feedback\n|Method Note\n)|\Z)", text, flags=re.DOTALL)
    why = ""
    if why_match:
        why = " | ".join(line[2:].strip() for line in why_match.group(1).splitlines() if line.strip().startswith("- "))
    return {
        "action": action_match.group(1) if action_match else "HOLD",
        "calorie_adjustment": int(adjustment_match.group(1)) if adjustment_match else 0,
        "analysis_end_date": end_match.group(1) if end_match else None,
        "phase": phase_match.group(1) if phase_match else "cut",
        "target_intake": _extract_number(text, "model target intake"),
        "estimated_tdee": _extract_number(text, "consensus planning maintenance") or _extract_number(text, "rolling 28-day estimated maintenance"),
        "target_deficit": _extract_number(text, "model target deficit"),
        "reason": why,
    }


def _load_history() -> pd.DataFrame:
    if HISTORY_PATH.exists():
        try:
            history = pd.read_csv(HISTORY_PATH)
        except Exception:
            history = pd.DataFrame()
    else:
        history = pd.DataFrame()
    for column in HISTORY_COLUMNS:
        if column not in history.columns:
            history[column] = pd.NA
    return history[HISTORY_COLUMNS].copy()


def _strength_summary_at(end_date: date) -> tuple[int, int, int]:
    if not STRENGTH_CSV.exists():
        return 0, 0, 0
    try:
        frame = pd.read_csv(STRENGTH_CSV)
    except Exception:
        return 0, 0, 0
    required = {"week_start", "target_lift", "estimated_1rm"}
    if frame.empty or not required.issubset(frame.columns):
        return 0, 0, 0
    frame["week_start"] = pd.to_datetime(frame["week_start"], errors="coerce").dt.date
    frame["estimated_1rm"] = pd.to_numeric(frame["estimated_1rm"], errors="coerce")
    frame = frame[frame["week_start"].notna() & frame["estimated_1rm"].notna()]
    current_start = end_date - timedelta(days=27)
    prior_end = current_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=27)
    current = frame[frame["week_start"].between(current_start, end_date)]
    prior = frame[frame["week_start"].between(prior_start, prior_end)]
    up = flat = down = 0
    for lift in set(current["target_lift"]).intersection(set(prior["target_lift"])):
        delta = float(current.loc[current["target_lift"] == lift, "estimated_1rm"].max()) - float(prior.loc[prior["target_lift"] == lift, "estimated_1rm"].max())
        if delta > 1.0:
            up += 1
        elif delta < -1.0:
            down += 1
        else:
            flat += 1
    return up, flat, down


def _window_metrics(con: duckdb.DuckDBPyConnection, start_date: date, end_date: date) -> dict[str, Any]:
    frame = con.execute(
        """
        SELECT
            dm.date, b.weight_kg, b.fat_mass_kg, b.lean_mass_kg,
            n.calories, n.protein_g, f.steps, f.sleep_hours, f.resting_hr, f.hrv,
            t.workout_count,
            p.grip_overall_best_kg, p.waist_cm
        FROM analytics.daily_metrics dm
        LEFT JOIN clean.body_composition b ON dm.date=b.date
        LEFT JOIN clean.nutrition_daily n ON dm.date=n.date
        LEFT JOIN clean.fitbit_daily f ON dm.date=f.date
        LEFT JOIN clean.training_summary t ON dm.date=t.date
        LEFT JOIN clean.performance_markers_daily p ON dm.date=p.date
        WHERE dm.date BETWEEN ?::DATE AND ?::DATE
        ORDER BY dm.date
        """,
        [start_date, end_date],
    ).fetchdf()

    def mean(column: str) -> float | None:
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        return None if values.empty else float(values.mean())

    def latest(column: str) -> float | None:
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        return None if values.empty else float(values.iloc[-1])

    workouts = pd.to_numeric(frame["workout_count"], errors="coerce").dropna()
    return {
        "body_days": int(frame["weight_kg"].notna().sum()),
        "sleep_days": int(frame["sleep_hours"].notna().sum()),
        "weight": mean("weight_kg"), "fat": mean("fat_mass_kg"), "lean": mean("lean_mass_kg"),
        "calories": mean("calories"), "protein": mean("protein_g"), "steps": mean("steps"),
        "sleep": mean("sleep_hours"), "rhr": mean("resting_hr"), "hrv": mean("hrv"),
        "workouts": float(workouts.sum()) if not workouts.empty else 0.0,
        "grip": latest("grip_overall_best_kg"), "waist": latest("waist_cm"),
    }


def _calorie_adherence(action: str, recommendation: float, actual_change: float | None) -> str:
    if actual_change is None:
        return "UNKNOWN"
    if action == "HOLD" or abs(recommendation) < 25:
        return "FOLLOWED" if abs(actual_change) <= 150 else "NOT_FOLLOWED"
    if actual_change * recommendation <= 0:
        return "NOT_FOLLOWED"
    ratio = abs(actual_change) / abs(recommendation)
    return "FOLLOWED" if ratio >= 0.5 else "PARTIAL"


def _target_adherence(actual: float | None, target: float | None, tolerance: float = 0.95) -> str:
    if actual is None or target is None:
        return "UNKNOWN"
    return "FOLLOWED" if actual >= target * tolerance else "NOT_FOLLOWED"


def _confounded(history: pd.DataFrame, event_index: int, decision_date: date, due_date: date) -> bool:
    for idx, row in history.iterrows():
        if idx == event_index:
            continue
        other = pd.to_datetime(row["decision_date"], errors="coerce")
        adjustment = _float(row["calorie_adjustment"]) or 0.0
        if pd.isna(other) or abs(adjustment) < 25:
            continue
        if decision_date < other.date() < due_date:
            return True
    return False


def _classify(action: str, calorie_adherence: str, metrics: dict[str, Any], baseline: dict[str, float | None], strength_down: int, confounded: bool) -> tuple[str, dict[str, float | None]]:
    deltas: dict[str, float | None] = {}
    for key in ["weight", "fat", "lean", "sleep", "rhr", "hrv", "steps", "calories", "waist"]:
        post, before = metrics.get(key), baseline.get(key)
        deltas[key] = None if post is None or before is None else post - before
    grip_delta_pct = None
    if metrics.get("grip") is not None and baseline.get("grip") not in (None, 0):
        grip_delta_pct = (float(metrics["grip"]) / float(baseline["grip"]) - 1.0) * 100.0
    deltas["grip_pct"] = grip_delta_pct

    if metrics["body_days"] < 3 or metrics["sleep_days"] < 4:
        return "INSUFFICIENT_DATA", deltas
    if confounded or calorie_adherence in {"UNKNOWN", "NOT_FOLLOWED"}:
        return "INCONCLUSIVE", deltas

    recovery_flags = 0
    if deltas["sleep"] is not None and deltas["sleep"] < -0.5:
        recovery_flags += 1
    if deltas["rhr"] is not None and deltas["rhr"] > 3:
        recovery_flags += 1
    if deltas["hrv"] is not None and deltas["hrv"] < -3:
        recovery_flags += 1
    grip_concern = grip_delta_pct is not None and grip_delta_pct < -8.0
    preservation_concern = (
        deltas["lean"] is not None and deltas["lean"] < -0.75 and strength_down >= 2
    ) or grip_concern

    if action == "INCREASE":
        if deltas["fat"] is not None and deltas["fat"] <= 0.15 and (deltas["lean"] is None or deltas["lean"] >= -0.35) and strength_down <= 1 and recovery_flags <= 1 and not grip_concern:
            return "HELPFUL", deltas
        if (deltas["fat"] is not None and deltas["fat"] > 0.60) or preservation_concern or recovery_flags >= 2:
            return "ADVERSE", deltas
        return "NEUTRAL", deltas
    if action == "DECREASE":
        if deltas["fat"] is not None and deltas["fat"] <= -0.20 and (deltas["lean"] is None or deltas["lean"] >= -0.40) and strength_down <= 1 and recovery_flags <= 1 and not grip_concern:
            return "HELPFUL", deltas
        if preservation_concern or strength_down >= 2 or recovery_flags >= 2:
            return "ADVERSE", deltas
        return "NEUTRAL", deltas
    if deltas["fat"] is not None and deltas["fat"] <= -0.15 and (deltas["lean"] is None or deltas["lean"] >= -0.40) and strength_down <= 1 and recovery_flags <= 1 and not grip_concern:
        return "HELPFUL", deltas
    if preservation_concern or strength_down >= 2 or recovery_flags >= 2:
        return "ADVERSE", deltas
    return "NEUTRAL", deltas


def _evaluate_history(history: pd.DataFrame, analysis_end: date) -> pd.DataFrame:
    if history.empty:
        return history
    con = duckdb.connect(str(DB_PATH), read_only=True)
    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        for idx, row in history.iterrows():
            parsed_date = pd.to_datetime(row["decision_date"], errors="coerce")
            if pd.isna(parsed_date):
                continue
            decision_date = parsed_date.date()
            action = str(row["action"] or "HOLD").upper()
            recommendation = _float(row["calorie_adjustment"]) or 0.0
            baseline = {
                "weight": _float(row["baseline_weight"]), "fat": _float(row["baseline_fat"]),
                "lean": _float(row["baseline_lean"]), "sleep": _float(row["baseline_sleep"]),
                "rhr": _float(row["baseline_rhr"]), "hrv": _float(row["baseline_hrv"]),
                "steps": _float(row["baseline_steps"]), "calories": _float(row["baseline_calories"]),
                "grip": _float(row["baseline_grip_kg"]), "waist": _float(row["baseline_waist_cm"]),
            }
            for horizon, first_day, last_day in [(7, 1, 7), (14, 8, 14), (28, 21, 28)]:
                status_col = f"outcome{horizon}_status"
                existing = str(row.get(status_col, "") or "").upper()
                if existing in {"HELPFUL", "NEUTRAL", "ADVERSE", "INCONCLUSIVE", "INSUFFICIENT_DATA"}:
                    continue
                due_date = decision_date + timedelta(days=last_day)
                if analysis_end < due_date:
                    continue

                metrics = _window_metrics(con, decision_date + timedelta(days=first_day), due_date)
                strength_up, strength_flat, strength_down = _strength_summary_at(due_date)
                calorie_change = None if metrics["calories"] is None or baseline["calories"] is None else metrics["calories"] - baseline["calories"]
                calorie_adherence = _calorie_adherence(action, recommendation, calorie_change)
                protein_adherence = _target_adherence(metrics["protein"], _float(row["target_protein_min"]))
                sleep_target = _float(row["target_sleep_h"])
                sleep_adherence = "UNKNOWN" if metrics["sleep"] is None or sleep_target is None else ("FOLLOWED" if metrics["sleep"] >= sleep_target - 0.2 else "NOT_FOLLOWED")
                training_adherence = _target_adherence(metrics["workouts"], _float(row["target_workouts"]), 1.0)
                steps_adherence = _target_adherence(metrics["steps"], _float(row["target_steps"]), 0.9)
                confounded = _confounded(history, idx, decision_date, due_date)
                status, deltas = _classify(action, calorie_adherence, metrics, baseline, strength_down, confounded)

                values = {
                    "status": status, "evaluated_date": str(due_date),
                    "calorie_adherence": calorie_adherence, "protein_adherence": protein_adherence,
                    "sleep_adherence": sleep_adherence, "training_adherence": training_adherence,
                    "steps_adherence": steps_adherence,
                    "actual_calories": metrics["calories"], "actual_protein": metrics["protein"],
                    "actual_sleep": metrics["sleep"], "actual_workouts": metrics["workouts"],
                    "actual_steps": metrics["steps"], "calorie_change": deltas["calories"],
                    "weight_delta": deltas["weight"], "fat_delta": deltas["fat"],
                    "lean_delta": deltas["lean"], "sleep_delta": deltas["sleep"],
                    "rhr_delta": deltas["rhr"], "hrv_delta": deltas["hrv"],
                    "steps_delta": deltas["steps"], "grip_delta_pct": deltas["grip_pct"],
                    "waist_delta_cm": deltas["waist"], "strength_up": strength_up,
                    "strength_flat": strength_flat, "strength_down": strength_down,
                    "confounded": confounded,
                }
                for field, value in values.items():
                    history.at[idx, f"outcome{horizon}_{field}"] = value
                history.at[idx, "updated_at_utc"] = now_utc
    finally:
        con.close()
    return history


def _feedback_evidence(history: pd.DataFrame, action: str) -> dict[str, Any]:
    result = {"eligible": 0, "helpful": 0, "neutral": 0, "adverse": 0, "helpful_rate": None, "adverse_rate": None, "status": "BUILDING", "horizon": EFFECTIVENESS_HORIZON}
    if history.empty:
        return result
    subset = history[history["action"].astype(str).str.upper() == action.upper()].copy()
    prefix = f"outcome{EFFECTIVENESS_HORIZON}_"
    subset = subset[
        subset[prefix + "status"].astype(str).isin(["HELPFUL", "NEUTRAL", "ADVERSE"])
        & subset[prefix + "calorie_adherence"].astype(str).isin(["FOLLOWED", "PARTIAL"])
    ]
    confounded = subset[prefix + "confounded"].astype(str).str.lower().isin(["true", "1"])
    subset = subset[~confounded]
    result["eligible"] = int(len(subset))
    if subset.empty:
        return result
    counts = subset[prefix + "status"].value_counts()
    for key in ["HELPFUL", "NEUTRAL", "ADVERSE"]:
        result[key.lower()] = int(counts.get(key, 0))
    result["helpful_rate"] = result["helpful"] / len(subset)
    result["adverse_rate"] = result["adverse"] / len(subset)
    result["status"] = "READY" if len(subset) >= MIN_FEEDBACK_EVENTS else "BUILDING"
    return result


def _rewrite_recommendation(text: str, action: str, original_adjustment: int, final_adjustment: int, evidence: dict[str, Any]) -> str:
    if final_adjustment != original_adjustment:
        text = re.sub(r"^Calorie adjustment:\s*[+-]?\d+\s*kcal/day\s*$", f"Calorie adjustment: {final_adjustment:+d} kcal/day", text, flags=re.MULTILINE)
        if action == "INCREASE":
            text = re.sub(r"Add about \d+ kcal/day for the next week", f"Add about {final_adjustment} kcal/day for the next week", text)
        elif action == "DECREASE":
            text = re.sub(r"Reduce by about \d+ kcal/day for the next week", f"Reduce by about {abs(final_adjustment)} kcal/day for the next week", text)
    feedback_lines = [
        "Adaptive Feedback", "-----------------",
        f"eligible followed {action.lower()} outcomes: {evidence['eligible']}",
        f"helpful={evidence['helpful']} | neutral={evidence['neutral']} | adverse={evidence['adverse']}",
        f"feedback-learning status: {evidence['status']}",
        (f"Repeated prior outcomes dampened this week's adjustment from {original_adjustment:+d} to {final_adjustment:+d} kcal/day." if final_adjustment != original_adjustment else "Feedback history is not currently overriding the model's calorie step."),
    ]
    block = "\n".join(feedback_lines) + "\n\n"
    marker = "\nMethod Note\n-----------"
    return text.replace(marker, "\n" + block + "Method Note\n-----------", 1) if marker in text else text.rstrip() + "\n\n" + block


def _upsert_event(history: pd.DataFrame, parsed: dict[str, Any], context: dict[str, Any], final_adjustment: int) -> pd.DataFrame:
    weekly = context.get("weekly", {})
    performance = context.get("performance", {})
    strength = context.get("strength_4w", [])
    strength_up, strength_flat, strength_down = (
        sum(1 for item in strength if item.get("direction") == "up"),
        sum(1 for item in strength if item.get("direction") == "flat"),
        sum(1 for item in strength if item.get("direction") == "down"),
    )
    lean = weekly.get("recent_lean")
    protein_target = float(lean) * 1.8 if lean is not None else 140.0
    decision_date = datetime.now(timezone.utc).date()
    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    key = str(decision_date)
    matches = history.index[history["decision_date"].astype(str) == key].tolist()
    values = {
        "decision_id": f"{key}-{parsed['action'].lower()}-{final_adjustment:+d}",
        "decision_date": key, "analysis_end_date": parsed["analysis_end_date"],
        "phase": parsed.get("phase", "cut"), "action": parsed["action"],
        "calorie_adjustment": final_adjustment, "target_intake": parsed["target_intake"],
        "estimated_tdee": parsed["estimated_tdee"], "target_deficit": parsed["target_deficit"],
        "target_protein_min": round(protein_target), "target_sleep_h": 7.0,
        "target_workouts": 2.0, "target_steps": 7000.0,
        "baseline_calories": weekly.get("recent_calories"), "baseline_protein": weekly.get("recent_protein"),
        "baseline_weight": weekly.get("recent_weight"), "baseline_fat": weekly.get("recent_fat"),
        "baseline_lean": weekly.get("recent_lean"), "baseline_sleep": weekly.get("recent_sleep"),
        "baseline_rhr": weekly.get("recent_rhr"), "baseline_hrv": weekly.get("recent_hrv"),
        "baseline_steps": weekly.get("recent_steps"), "baseline_grip_kg": performance.get("latest_grip_overall_kg"),
        "baseline_waist_cm": performance.get("latest_waist_cm"),
        "baseline_strength_up": strength_up, "baseline_strength_flat": strength_flat, "baseline_strength_down": strength_down,
        "decision_reason": parsed["reason"], "updated_at_utc": now_utc,
    }
    if matches:
        idx = matches[0]
        created = history.at[idx, "created_at_utc"]
        for name, value in values.items():
            history.at[idx, name] = value
        if pd.isna(created):
            history.at[idx, "created_at_utc"] = now_utc
    else:
        row = {column: pd.NA for column in HISTORY_COLUMNS}
        row.update(values)
        row["created_at_utc"] = now_utc
        history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    sort_key = pd.to_datetime(history["decision_date"], errors="coerce")
    return history.assign(_sort=sort_key).sort_values("_sort").drop(columns="_sort").reset_index(drop=True)


def _report(history: pd.DataFrame, parsed: dict[str, Any], adjustment: int) -> str:
    decision_date = datetime.now(timezone.utc).date()
    current = history[history["decision_date"].astype(str) == str(decision_date)]
    current_row = current.iloc[-1] if not current.empty else None
    lines = [
        "Adaptive Coaching Feedback Loop", "===============================", "",
        "Current Decision", "----------------",
        f"decision date: {decision_date}", f"analysis data through: {parsed['analysis_end_date']}",
        f"phase: {parsed.get('phase', 'cut')}", f"action: {parsed['action']}",
        f"calorie adjustment: {adjustment:+d} kcal/day", f"model target intake: {_num(parsed['target_intake'], 0)} kcal/day",
    ]
    if current_row is not None:
        lines.extend([
            f"protein target: >= {_num(current_row['target_protein_min'], 0)} g/day",
            f"sleep target: >= {_num(current_row['target_sleep_h'], 1)} h/night",
            f"training target: >= {_num(current_row['target_workouts'], 0)} sessions/week",
            f"steps target: ~{_num(current_row['target_steps'], 0)}/day",
        ])
    lines.extend(["This decision and its supporting targets are logged for 7-day adherence/recovery, 14-day early direction, and days 21-28 effectiveness follow-up.", "", "Learning Status", "---------------"])
    for action in ["INCREASE", "DECREASE", "HOLD"]:
        evidence = _feedback_evidence(history, action)
        lines.append(f"{action}: {evidence['eligible']} eligible 21-28 day effectiveness outcome(s) | helpful={evidence['helpful']} neutral={evidence['neutral']} adverse={evidence['adverse']} | learning={evidence['status']}")

    lines.extend(["", "Recent Evaluations", "------------------"])
    evaluated = history[history["outcome7_status"].astype(str).isin(["HELPFUL", "NEUTRAL", "ADVERSE", "INCONCLUSIVE", "INSUFFICIENT_DATA"])].tail(4)
    if evaluated.empty:
        lines.append("No follow-up window has matured yet.")
    else:
        for _, row in evaluated.iterrows():
            lines.append(
                f"{row['decision_date']} {row['action']} {_float(row['calorie_adjustment']) or 0:+.0f}: "
                f"7d={row['outcome7_status']} | 14d={row.get('outcome14_status', 'PENDING')} | 21-28d={row.get('outcome28_status', 'PENDING')} | "
                f"calorie={row['outcome7_calorie_adherence']} | protein={row['outcome7_protein_adherence']} | "
                f"sleep={row['outcome7_sleep_adherence']} | training={row['outcome7_training_adherence']} | steps={row['outcome7_steps_adherence']} | "
                f"fat={_num(row['outcome7_fat_delta'])} kg | lean={_num(row['outcome7_lean_delta'])} kg | grip={_num(row['outcome7_grip_delta_pct'], 1)}%"
            )

    lines.extend([
        "", "Method Note", "-----------",
        "The feedback loop separates adherence from effectiveness. If a recommendation was not followed, its outcome is not treated as evidence that the recommendation itself failed.",
        "Calories are evaluated directionally; protein, sleep, two weekly resistance sessions, and roughly 7k daily steps are tracked as supporting adherence targets.",
        "Grip and waist are included when follow-up measurements exist. Grip decline is only treated as a preservation concern when the change is large enough to be meaningful; sparse waist data are descriptive context.",
        f"At least {MIN_FEEDBACK_EVENTS} eligible, followed, unconfounded days-21-to-28 effectiveness outcomes for the same action are required before history can dampen a future calorie step.",
    ])
    return "\n".join(lines)


def main() -> None:
    if not RECOMMENDATION_PATH.exists():
        raise RuntimeError("Adaptive calorie recommendation must run before feedback tracking.")
    text = RECOMMENDATION_PATH.read_text(encoding="utf-8")
    parsed = _parse_recommendation(text)
    if parsed["analysis_end_date"] is None:
        raise RuntimeError("Could not parse the recommendation reporting date.")
    context = load_report_context()
    analysis_end = context.get("analysis_end_date")
    if analysis_end is None:
        raise RuntimeError("No complete analysis date available.")

    history = _evaluate_history(_load_history(), analysis_end)
    evidence = _feedback_evidence(history, parsed["action"])
    original_adjustment = int(parsed["calorie_adjustment"])
    final_adjustment = original_adjustment
    if parsed["action"] in {"INCREASE", "DECREASE"} and evidence["status"] == "READY" and evidence["adverse_rate"] is not None and evidence["adverse_rate"] >= 0.50 and (evidence["helpful_rate"] or 0.0) < 0.25:
        final_adjustment = DAMPENED_ADJUSTMENT if original_adjustment > 0 else -DAMPENED_ADJUSTMENT

    revised_text = _rewrite_recommendation(text, parsed["action"], original_adjustment, final_adjustment, evidence)
    RECOMMENDATION_PATH.write_text(revised_text, encoding="utf-8")
    history = _upsert_event(history, parsed, context, final_adjustment)
    history.to_csv(HISTORY_PATH, index=False)

    feedback_text = _report(history, parsed, final_adjustment)
    FEEDBACK_REPORT.write_text(feedback_text, encoding="utf-8")
    payload = {
        "decision_date": str(datetime.now(timezone.utc).date()),
        "analysis_end_date": parsed["analysis_end_date"], "phase": parsed.get("phase", "cut"),
        "action": parsed["action"], "original_calorie_adjustment": original_adjustment,
        "final_calorie_adjustment": final_adjustment, "target_intake": parsed["target_intake"],
        "estimated_tdee": parsed["estimated_tdee"], "target_deficit": parsed["target_deficit"],
        "feedback_evidence": evidence,
    }
    RECOMMENDATION_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved: {HISTORY_PATH}")
    print(f"Saved: {FEEDBACK_REPORT}")
    print(f"Saved: {RECOMMENDATION_JSON}")
    print()
    print(feedback_text)


if __name__ == "__main__":
    main()
