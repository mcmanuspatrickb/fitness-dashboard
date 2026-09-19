from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Patch target not found: {label}")
    return text.replace(old, new, 1)


root = Path(__file__).resolve().parent

# --- Adaptive calorie model: 28/42-day TDEE consensus + slower personal-learning gate ---
p = root / "scripts" / "73_adaptive_calorie_recommendation.py"
text = p.read_text(encoding="utf-8")
text = replace_once(
    text,
    "import pandas as pd\n",
    "import duckdb\nimport pandas as pd\n",
    "73 import duckdb",
)
text = replace_once(
    text,
    'PROJECT_ROOT = Path(__file__).resolve().parent.parent\nREPORTS_DIR = PROJECT_ROOT / "reports"\n',
    'PROJECT_ROOT = Path(__file__).resolve().parent.parent\nDB_PATH = PROJECT_ROOT / "db" / "fitness.duckdb"\nREPORTS_DIR = PROJECT_ROOT / "reports"\n',
    "73 DB path",
)
text = replace_once(text, "MIN_PERSONAL_BLOCKS = 8", "MIN_PERSONAL_BLOCKS = 12", "73 personal gate")

insert_marker = "\ndef _spearman(frame: pd.DataFrame, x: str, y: str) -> float | None:\n"
load_window = '''\ndef _load_energy_window(end_date, days: int) -> pd.DataFrame:\n    con = duckdb.connect(str(DB_PATH), read_only=True)\n    try:\n        return con.execute(\n            \"\"\"\n            SELECT d.date, b.weight_kg, n.calories\n            FROM analytics.daily_metrics d\n            LEFT JOIN clean.body_composition b ON d.date=b.date\n            LEFT JOIN clean.nutrition_daily n ON d.date=n.date\n            WHERE d.date BETWEEN (?::DATE - (? - 1) * INTERVAL 1 DAY) AND ?::DATE\n            ORDER BY d.date\n            \"\"\",\n            [end_date, days, end_date],\n        ).fetchdf()\n    finally:\n        con.close()\n\n\ndef _round25_float(value: float) -> float:\n    return float(round(value / 25.0) * 25.0)\n\n'''
text = replace_once(text, insert_marker, load_window + insert_marker, "73 energy window helper")

old_energy = '''    energy = _rolling_energy_balance(trailing_28, recent_weight)\n    estimated_tdee = energy.get("estimated_tdee")\n    estimated_deficit = energy.get("estimated_deficit")\n    pace = energy.get("weight_loss_pct_week")\n    strength_up, strength_flat, strength_down = _strength_summary(strength)\n    personal = _load_personal_response()\n'''
new_energy = '''    energy = _rolling_energy_balance(trailing_28, recent_weight)\n    energy42 = _rolling_energy_balance(_load_energy_window(end_date, 42), recent_weight)\n    tdee28 = energy.get("estimated_tdee")\n    tdee42 = energy42.get("estimated_tdee")\n    available_tdee = [float(v) for v in (tdee28, tdee42) if v is not None]\n    tdee_difference = abs(float(tdee28) - float(tdee42)) if tdee28 is not None and tdee42 is not None else None\n    if len(available_tdee) == 2:\n        estimated_tdee = sum(available_tdee) / 2.0\n        tdee_stability = "STABLE" if tdee_difference <= 150 else ("WATCH" if tdee_difference <= 300 else "UNSTABLE")\n        planning_low = min(available_tdee) - 100.0\n        planning_high = max(available_tdee) + 100.0\n    elif len(available_tdee) == 1:\n        estimated_tdee = available_tdee[0]\n        tdee_stability = "SINGLE_WINDOW"\n        planning_low = estimated_tdee - 175.0\n        planning_high = estimated_tdee + 175.0\n    else:\n        estimated_tdee = None\n        tdee_stability = "UNAVAILABLE"\n        planning_low = planning_high = None\n    estimated_deficit = (estimated_tdee - float(energy.get("avg_calories"))) if estimated_tdee is not None and energy.get("avg_calories") is not None else None\n    pace = energy.get("weight_loss_pct_week")\n    strength_up, strength_flat, strength_down = _strength_summary(strength)\n    personal = _load_personal_response()\n    if tdee_stability == "UNSTABLE":\n        notes.append("The 28- and 42-day maintenance estimates disagree materially, so the model will not deepen the deficit from TDEE math this week.")\n'''
text = replace_once(text, old_energy, new_energy, "73 main TDEE block")

text = replace_once(
    text,
    '            elif proposed < 0 and stalled_loss and fat_not_moving and strength_stable and guardrail_status == "STABLE":\n',
    '            elif proposed < 0 and stalled_loss and fat_not_moving and strength_stable and guardrail_status == "STABLE" and tdee_stability != "UNSTABLE":\n',
    "73 unstable deficit guard",
)

old_report = '''        f"rolling 28-day estimated maintenance: {_fmt(estimated_tdee, 0)} kcal/day",\n        f"rolling 28-day estimated deficit: {_fmt(estimated_deficit, 0)} kcal/day",\n        f"rolling 28-day loss pace: {_fmt(pace, 2)}% body weight/week",\n        f"energy-balance coverage: {energy.get('coverage_confidence', 'LOW')} ({energy.get('calorie_days', 0)} nutrition days; {energy.get('weight_days', 0)} weight days)",\n        f"model target deficit: {_fmt(target_deficit, 0)} kcal/day",\n        f"model target intake: {_fmt(target_calories, 0)} kcal/day", "",\n'''
new_report = '''        f"rolling 28-day estimated maintenance: {_fmt(tdee28, 0)} kcal/day",\n        f"rolling 42-day estimated maintenance: {_fmt(tdee42, 0)} kcal/day",\n        f"consensus planning maintenance: {_fmt(estimated_tdee, 0)} kcal/day",\n        f"planning maintenance range: {_fmt(planning_low, 0)}-{_fmt(planning_high, 0)} kcal/day",\n        f"28/42-day TDEE agreement: {tdee_stability}",\n        f"consensus estimated deficit: {_fmt(estimated_deficit, 0)} kcal/day",\n        f"rolling 28-day loss pace: {_fmt(pace, 2)}% body weight/week",\n        f"energy-balance coverage (28d): {energy.get('coverage_confidence', 'LOW')} ({energy.get('calorie_days', 0)} nutrition days; {energy.get('weight_days', 0)} weight days)",\n        f"model target deficit: {_fmt(target_deficit, 0)} kcal/day",\n        f"model target intake: {_fmt(target_calories, 0)} kcal/day", "",\n'''
text = replace_once(text, old_report, new_report, "73 report TDEE block")
text = text.replace(
    "Maintenance/TDEE is inferred from the 28-day scale-weight trend plus logged calorie intake using 7,700 kcal per kg as an energy-balance approximation.",
    "Maintenance/TDEE is inferred from both 28- and 42-day scale-weight trends plus logged calorie intake using 7,700 kcal per kg as an energy-balance approximation. The planning estimate uses both windows when available and reports their disagreement as uncertainty.",
)
p.write_text(text, encoding="utf-8")

# --- Adaptive feedback: 7d adherence, 14d early direction, days 21-28 effectiveness ---
p = root / "scripts" / "76_adaptive_coaching_feedback.py"
text = p.read_text(encoding="utf-8")
text = replace_once(
    text,
    "MIN_FEEDBACK_EVENTS = 4\nDAMPENED_ADJUSTMENT = 50\n",
    "MIN_FEEDBACK_EVENTS = 4\nDAMPENED_ADJUSTMENT = 50\nEFFECTIVENESS_HORIZON = 28\n",
    "76 effectiveness horizon constant",
)
text = replace_once(text, "    for horizon in (7, 14)\n", "    for horizon in (7, 14, 28)\n", "76 history columns")
text = replace_once(
    text,
    "            for horizon, first_day, last_day in [(7, 1, 7), (14, 8, 14)]:\n",
    "            for horizon, first_day, last_day in [(7, 1, 7), (14, 8, 14), (28, 21, 28)]:\n",
    "76 evaluation windows",
)

old_feedback = '''def _feedback_evidence(history: pd.DataFrame, action: str) -> dict[str, Any]:\n    result = {"eligible": 0, "helpful": 0, "neutral": 0, "adverse": 0, "helpful_rate": None, "adverse_rate": None, "status": "BUILDING"}\n    if history.empty:\n        return result\n    subset = history[history["action"].astype(str).str.upper() == action.upper()].copy()\n    subset = subset[\n        subset["outcome7_status"].astype(str).isin(["HELPFUL", "NEUTRAL", "ADVERSE"])\n        & subset["outcome7_calorie_adherence"].astype(str).isin(["FOLLOWED", "PARTIAL"])\n    ]\n    confounded = subset["outcome7_confounded"].astype(str).str.lower().isin(["true", "1"])\n    subset = subset[~confounded]\n    result["eligible"] = int(len(subset))\n    if subset.empty:\n        return result\n    counts = subset["outcome7_status"].value_counts()\n    for key in ["HELPFUL", "NEUTRAL", "ADVERSE"]:\n        result[key.lower()] = int(counts.get(key, 0))\n    result["helpful_rate"] = result["helpful"] / len(subset)\n    result["adverse_rate"] = result["adverse"] / len(subset)\n    result["status"] = "READY" if len(subset) >= MIN_FEEDBACK_EVENTS else "BUILDING"\n    return result\n'''
new_feedback = '''def _feedback_evidence(history: pd.DataFrame, action: str) -> dict[str, Any]:\n    result = {"eligible": 0, "helpful": 0, "neutral": 0, "adverse": 0, "helpful_rate": None, "adverse_rate": None, "status": "BUILDING", "horizon": EFFECTIVENESS_HORIZON}\n    if history.empty:\n        return result\n    subset = history[history["action"].astype(str).str.upper() == action.upper()].copy()\n    prefix = f"outcome{EFFECTIVENESS_HORIZON}_"\n    subset = subset[\n        subset[prefix + "status"].astype(str).isin(["HELPFUL", "NEUTRAL", "ADVERSE"])\n        & subset[prefix + "calorie_adherence"].astype(str).isin(["FOLLOWED", "PARTIAL"])\n    ]\n    confounded = subset[prefix + "confounded"].astype(str).str.lower().isin(["true", "1"])\n    subset = subset[~confounded]\n    result["eligible"] = int(len(subset))\n    if subset.empty:\n        return result\n    counts = subset[prefix + "status"].value_counts()\n    for key in ["HELPFUL", "NEUTRAL", "ADVERSE"]:\n        result[key.lower()] = int(counts.get(key, 0))\n    result["helpful_rate"] = result["helpful"] / len(subset)\n    result["adverse_rate"] = result["adverse"] / len(subset)\n    result["status"] = "READY" if len(subset) >= MIN_FEEDBACK_EVENTS else "BUILDING"\n    return result\n'''
text = replace_once(text, old_feedback, new_feedback, "76 feedback evidence")
text = text.replace(
    "This decision and its supporting targets are logged for 7-day and 14-day follow-up.",
    "This decision and its supporting targets are logged for 7-day adherence/recovery, 14-day early direction, and days 21-28 effectiveness follow-up.",
)
text = text.replace(
    "eligible 7-day outcome(s)",
    "eligible 21-28 day effectiveness outcome(s)",
)
old_recent = '''                f"7d={row['outcome7_status']} | calorie={row['outcome7_calorie_adherence']} | "\n                f"protein={row['outcome7_protein_adherence']} | sleep={row['outcome7_sleep_adherence']} | "\n                f"training={row['outcome7_training_adherence']} | steps={row['outcome7_steps_adherence']} | "\n                f"fat={_num(row['outcome7_fat_delta'])} kg | lean={_num(row['outcome7_lean_delta'])} kg | grip={_num(row['outcome7_grip_delta_pct'], 1)}%"\n'''
new_recent = '''                f"7d={row['outcome7_status']} | 14d={row.get('outcome14_status', 'PENDING')} | 21-28d={row.get('outcome28_status', 'PENDING')} | "\n                f"calorie={row['outcome7_calorie_adherence']} | protein={row['outcome7_protein_adherence']} | "\n                f"sleep={row['outcome7_sleep_adherence']} | training={row['outcome7_training_adherence']} | steps={row['outcome7_steps_adherence']} | "\n                f"fat={_num(row['outcome7_fat_delta'])} kg | lean={_num(row['outcome7_lean_delta'])} kg | grip={_num(row['outcome7_grip_delta_pct'], 1)}%"\n'''
text = replace_once(text, old_recent, new_recent, "76 recent evaluations")
text = text.replace(
    "At least {MIN_FEEDBACK_EVENTS} eligible, followed, unconfounded seven-day calorie outcomes for the same action are required before history can dampen a future calorie step.",
    "At least {MIN_FEEDBACK_EVENTS} eligible, followed, unconfounded days-21-to-28 effectiveness outcomes for the same action are required before history can dampen a future calorie step.",
)
p.write_text(text, encoding="utf-8")

print("Patched adaptive calorie and feedback models.")
