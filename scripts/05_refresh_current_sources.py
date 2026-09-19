from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

STATUS_JSON = REPORTS_DIR / "source_refresh_status.json"
STATUS_TXT = REPORTS_DIR / "source_refresh_status.txt"

SOURCES = [
    {
        "name": "withings",
        "script": "12_sync_withings_persistent.py",
        "required_env": ["WITHINGS_DATABASE_URL"],
        "description": "Direct Withings measurements from the persistent database",
        "max_attempts": 1,
    },
    {
        "name": "grip",
        "script": "16_sync_grip_persistent.py",
        "required_env": ["WITHINGS_DATABASE_URL"],
        "description": "Grip-strength measurements shared with the Health Dashboard persistent database",
        "max_attempts": 1,
    },
    {
        "name": "google_health",
        "script": "18_ingest_google_health.py",
        "required_env": [
            "GOOGLE_HEALTH_CLIENT_ID",
            "GOOGLE_HEALTH_CLIENT_SECRET",
            "GOOGLE_HEALTH_REFRESH_TOKEN",
        ],
        "description": "Google Health activity, recovery, sleep, and Cronometer nutrition",
        "max_attempts": 4,
    },
    {
        "name": "hevy",
        "script": "15_ingest_hevy_current.py",
        "required_env": ["HEVY_API_KEY"],
        "description": "Current Hevy workouts, sets, and body measurements such as waist",
        "max_attempts": 1,
    },
]

TRANSIENT_ERROR_MARKERS = (
    " 429 ", "(429)", '"code": 429',
    " 500 ", "(500)", '"code": 500',
    " 502 ", "(502)", '"code": 502',
    " 503 ", "(503)", '"code": 503',
    " 504 ", "(504)", '"code": 504',
    "unavailable", "temporarily unavailable", "timeout", "timed out",
    "connection reset", "connection aborted", "remote disconnected",
)


def _is_transient_failure(stdout: str, stderr: str) -> bool:
    text = f"{stdout}\n{stderr}".lower()
    return any(marker in text for marker in TRANSIENT_ERROR_MARKERS)


def run_source(source: dict) -> dict:
    missing = [name for name in source["required_env"] if not os.getenv(name, "").strip()]
    result = {
        "name": source["name"], "description": source["description"],
        "script": source["script"], "required_env": source["required_env"],
        "missing_env": missing, "status": "skipped" if missing else "pending",
        "returncode": None, "stdout": "", "stderr": "", "attempts": 0,
        "retry_log": [],
    }
    if missing:
        return result

    script_path = SCRIPTS_DIR / source["script"]
    if not script_path.exists():
        result["status"] = "failed"
        result["stderr"] = f"Missing script: {script_path}"
        return result

    max_attempts = max(1, int(source.get("max_attempts", 1)))
    for attempt in range(1, max_attempts + 1):
        completed = subprocess.run(
            [sys.executable, str(script_path)], cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, check=False, env=os.environ.copy(),
        )
        result["attempts"] = attempt
        result["returncode"] = completed.returncode
        result["stdout"] = completed.stdout[-12000:]
        result["stderr"] = completed.stderr[-12000:]
        if completed.returncode == 0:
            result["status"] = "success"
            return result

        result["status"] = "failed"
        transient = _is_transient_failure(completed.stdout, completed.stderr)
        if not transient or attempt >= max_attempts:
            return result
        delay_seconds = min(60, 5 * (2 ** (attempt - 1)))
        result["retry_log"].append(
            f"Attempt {attempt} failed with a transient API/network error; retrying in {delay_seconds}s."
        )
        time.sleep(delay_seconds)
    return result


def main() -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [run_source(source) for source in SOURCES],
    }
    STATUS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = ["Current Source Refresh", "======================", f"Generated: {payload['generated_at']}", ""]
    for source in payload["sources"]:
        lines.append(f"{source['name']}: {source['status'].upper()}")
        lines.append(f"  {source['description']}")
        if source["attempts"]:
            lines.append(f"  Attempts: {source['attempts']}")
        if source["missing_env"]:
            lines.append("  Missing configuration: " + ", ".join(source["missing_env"]))
        for retry_line in source.get("retry_log", []):
            lines.append(f"  {retry_line}")
        if source["stdout"].strip():
            lines.append("  Output:")
            for line in source["stdout"].strip().splitlines()[-12:]:
                lines.append(f"    {line}")
        if source["stderr"].strip():
            lines.append("  Error output:")
            for line in source["stderr"].strip().splitlines()[-12:]:
                lines.append(f"    {line}")
        lines.append("")

    STATUS_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"Saved: {STATUS_JSON}")
    print(f"Saved: {STATUS_TXT}")


if __name__ == "__main__":
    main()
