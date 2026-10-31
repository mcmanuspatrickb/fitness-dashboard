"""Manual, read-only Hevy and Google Health exercise-session mirror to Neon.

Records individual workouts and activity intervals without changing the existing
daily energy totals. Uses existing secrets and no new paid service.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

BERLIN = ZoneInfo("Europe/Berlin")
HEVY_API = "https://api.hevyapp.com/v1/workouts"
GOOGLE_API = "https://health.googleapis.com/v4"


def parse_instant(raw):
    if isinstance(raw, (int, float)):
        epoch = float(raw)
        return datetime.fromtimestamp(epoch / 1000 if epoch > 1e11 else epoch, timezone.utc)
    if not isinstance(raw, str) or not raw.strip():
        return None
    if raw.isdecimal():
        return parse_instant(int(raw))
    try:
        dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (ValueError, OverflowError):
        return None


def google_interval(interval, *, end=False):
    key = "endTime" if end else "startTime"
    direct = parse_instant(interval.get(key))
    if direct:
        return direct
    civil = interval.get("civilEndTime" if end else "civilStartTime", {}) or {}
    d, t = civil.get("date", {}) or {}, civil.get("time", {}) or {}
    try:
        naive = datetime(int(d["year"]), int(d["month"]), int(d["day"]),
                         int(t.get("hours", 0)), int(t.get("minutes", 0)),
                         int(t.get("seconds", 0)))
        # A repeated local hour at the DST transition cannot be assigned safely.
        if naive.replace(tzinfo=BERLIN, fold=0).utcoffset() != naive.replace(tzinfo=BERLIN, fold=1).utcoffset():
            return None
        return naive.replace(tzinfo=BERLIN).astimezone(timezone.utc)
    except (ValueError, TypeError, KeyError):
        return None


def hevy_rows(workouts):
    sessions, sets = [], []
    for w in workouts:
        wid = str(w.get("id") or w.get("workout_id") or "").strip()
        start = parse_instant(w.get("start_time") or w.get("startTime") or w.get("started_at"))
        end = parse_instant(w.get("end_time") or w.get("endTime") or w.get("ended_at"))
        if not wid or not start or not end or end < start:
            continue
        sessions.append((wid, start, end, str(w.get("title") or "Workout")[:250],
                         str(w.get("description") or "")[:2000]))
        for ex_no, ex in enumerate(w.get("exercises") or w.get("workout_exercises") or []):
            title = str(ex.get("title") or ex.get("name") or "Exercise")[:250]
            for set_no, record in enumerate(ex.get("sets") or []):
                try:
                    weight = float(record["weight_kg"]) if record.get("weight_kg") is not None else None
                    reps = float(record["reps"]) if record.get("reps") is not None else None
                    rpe = float(record["rpe"]) if record.get("rpe") is not None else None
                except (TypeError, ValueError):
                    continue
                if rpe is not None and not 0 <= rpe <= 10:
                    rpe = None
                sets.append((f"{wid}:{ex_no}:{set_no}", wid, title, ex_no, set_no,
                             str(record.get("type") or "normal").lower()[:40], weight, reps, rpe))
    return sessions, sets


def google_exercise_rows(points):
    rows = []
    for point in points:
        ex = point.get("exercise") or {}
        interval = ex.get("interval") or {}
        start = google_interval(interval)
        end = google_interval(interval, end=True)
        if not start or not end or not start < end or end - start > timedelta(days=3):
            continue
        source = point.get("dataSource") or {}
        platform = str(source.get("platform") or "unknown")[:80]
        package = str((source.get("application") or {}).get("packageName") or "")[:200]
        category = str(ex.get("exerciseType") or "UNKNOWN")[:100]
        title = str(ex.get("displayName") or category)[:250]
        metrics = ex.get("metricsSummary") or {}
        try:
            avg_hr = float(metrics["averageHeartRateBeatsPerMinute"]) if metrics.get("averageHeartRateBeatsPerMinute") is not None else None
        except (TypeError, ValueError):
            avg_hr = None
        fingerprint = "|".join([start.isoformat(), end.isoformat(), category, platform, package])
        source_key = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        rows.append((source_key, start, end, category, title, platform, package, avg_hr))
    return rows


def fetch_hevy():
    key = os.environ.get("HEVY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("HEVY_API_KEY not configured")
    output = []
    for page in range(1, 101):
        response = requests.get(HEVY_API,
            headers={"api-key": key, "accept": "application/json"},
            params={"page": page, "pageSize": 10}, timeout=45)
        response.raise_for_status()
        payload = response.json()
        batch = payload.get("workouts") or payload.get("data") or []
        if not isinstance(batch, list) or not batch:
            break
        output.extend(batch)
        total_pages = payload.get("page_count") or payload.get("pageCount")
        if len(batch) < 10 or (total_pages is not None and page >= int(total_pages)):
            break
    return output


def google_token():
    required = ("GOOGLE_HEALTH_CLIENT_ID", "GOOGLE_HEALTH_CLIENT_SECRET",
                "GOOGLE_HEALTH_REFRESH_TOKEN")
    if any(not os.getenv(k) for k in required):
        raise RuntimeError("Google Health credentials not configured")
    resp = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": os.environ[required[0]],
        "client_secret": os.environ[required[1]],
        "refresh_token": os.environ[required[2]],
        "grant_type": "refresh_token"})
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_google_exercises(start: date, end: date):
    token = google_token()
    points = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=14), end + timedelta(days=1))
        filter_expr = (
            f'exercise.interval.civil_start_time >= "{chunk_start.isoformat()}" '
            f'AND exercise.interval.civil_start_time < "{chunk_end.isoformat()}"'
        )
        cursor = None
        while True:
            params = {"page_size": 100, "filter": filter_expr,
                      "dataSourceFamily": "users/me/dataSourceFamilies/all-sources"}
            if cursor:
                params["page_token"] = cursor
            resp = requests.get(
                f"{GOOGLE_API}/users/me/dataTypes/exercise/dataPoints:reconcile",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            points.extend(data.get("dataPoints") or [])
            cursor = data.get("nextPageToken")
            if not cursor:
                break
        chunk_start = chunk_end
    return points


def persist(sessions, sets, exercises):
    import psycopg
    url = os.getenv("WITHINGS_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("WITHINGS_DATABASE_URL missing")
    with psycopg.connect(url) as conn, conn.cursor() as cur:
        conn.execute("""CREATE TABLE IF NOT EXISTS hevy_workout_sessions (
            workout_id TEXT PRIMARY KEY, start_at TIMESTAMPTZ NOT NULL,
            end_at TIMESTAMPTZ NOT NULL, title TEXT NOT NULL, description TEXT,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        conn.execute("""CREATE TABLE IF NOT EXISTS hevy_workout_sets (
            set_key TEXT PRIMARY KEY,
            workout_id TEXT NOT NULL REFERENCES hevy_workout_sessions(workout_id),
            exercise_title TEXT, exercise_index INTEGER, set_index INTEGER,
            set_type TEXT, weight_kg DOUBLE PRECISION, reps DOUBLE PRECISION,
            rpe DOUBLE PRECISION, synced_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        conn.execute("""CREATE TABLE IF NOT EXISTS google_health_exercise_sessions (
            source_key TEXT PRIMARY KEY, start_at TIMESTAMPTZ NOT NULL,
            end_at TIMESTAMPTZ NOT NULL, exercise_type TEXT, title TEXT,
            platform TEXT, package_name TEXT, avg_heart_rate_bpm DOUBLE PRECISION,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        if sessions:
            cur.executemany("""INSERT INTO hevy_workout_sessions
                (workout_id,start_at,end_at,title,description) VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT(workout_id) DO UPDATE SET start_at=excluded.start_at,
                end_at=excluded.end_at,title=excluded.title,description=excluded.description,
                synced_at=now()""", sessions)
        if sets:
            cur.executemany("""INSERT INTO hevy_workout_sets
                (set_key,workout_id,exercise_title,exercise_index,set_index,set_type,weight_kg,reps,rpe)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(set_key) DO UPDATE SET exercise_title=excluded.exercise_title,
                set_type=excluded.set_type,weight_kg=excluded.weight_kg,
                reps=excluded.reps,rpe=excluded.rpe,synced_at=now()""", sets)
        if exercises:
            cur.executemany("""INSERT INTO google_health_exercise_sessions
                (source_key,start_at,end_at,exercise_type,title,platform,package_name,avg_heart_rate_bpm)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(source_key) DO UPDATE SET
                title=excluded.title,avg_heart_rate_bpm=excluded.avg_heart_rate_bpm,
                synced_at=now()""", exercises)
    print(f"Exercise timeline synced: hevy_sessions={len(sessions)}, hevy_sets={len(sets)}, google_exercises={len(exercises)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.days <= 365:
        parser.error("--days must be 1..365")
    end = datetime.now(BERLIN).date()
    start = end - timedelta(days=args.days - 1)
    sessions, sets = hevy_rows(fetch_hevy())
    exercises = google_exercise_rows(fetch_google_exercises(start, end))
    if args.dry_run:
        print(f"Dry run: {len(sessions)} Hevy sessions, {len(sets)} sets, {len(exercises)} exercises")
    else:
        persist(sessions, sets, exercises)


if __name__ == "__main__":
    main()
