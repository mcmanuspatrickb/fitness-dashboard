from __future__ import annotations

import json
import os
import subprocess
import sys
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
    },
    {
        "name": "hevy",
        "script": "15_ingest_hevy_current.py",
        "required_env": ["HEVY_API_KEY"],
        "description": "Current paginated Hevy workout history",
    },
]


def run_source(source: dict) -> dict:
    missing = [name for name in source["required_env"] if not os.getenv(name, "").strip()]
    result = {
        "name": source["name"],
        "description": source["description"],
        "script": source["script"],
        "required_env": source["required_env"],
        "missing_env": missing,
        "status": "skipped" if missing else "pending",
        "returncode": None,
        "stdout": "",
        "stderr": "",
    }

    if missing:
        return result

    script_path = SCRIPTS_DIR / source["script"]
    if not script_path.exists():
        result["status"] = "failed"
        result["stderr"] = f"Missing script: {script_path}"
        return result

    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )
    result["returncode"] = completed.returncode
    result["stdout"] = completed.stdout[-12000:]
    result["stderr"] = completed.stderr[-12000:]
    result["status"] = "success" if completed.returncode == 0 else "failed"
    return result


def main() -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": [run_source(source) for source in SOURCES],
    }

    STATUS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "Current Source Refresh",
        "======================",
        f"Generated: {payload['generated_at']}",
        "",
    ]

    for source in payload["sources"]:
        lines.append(f"{source['name']}: {source['status'].upper()}")
        lines.append(f"  {source['description']}")
        if source["missing_env"]:
            lines.append("  Missing configuration: " + ", ".join(source["missing_env"]))
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
