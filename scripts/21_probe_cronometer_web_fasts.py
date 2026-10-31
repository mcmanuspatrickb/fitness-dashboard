"""Read-only Cronometer WEB fasting probe against the user's account.

No fasting records, credentials, cookies or server responses are logged or
persisted. Uses pinned, inspectable community implementation of GWT-RPC.
This is an isolated diagnostic, NOT a production fasting importer.
"""
from datetime import date
import os
import sys

def main():
    # All auth state stays on the ephemeral GitHub Actions runner.
    from cronometer_mcp.client import CronometerClient
    if not os.getenv("CRONOMETER_USERNAME") or not os.getenv("CRONOMETER_PASSWORD"):
        raise RuntimeError("Required Cronometer secrets not provided")
    client = CronometerClient()
    try:
        # Authenticate only once; may be rate-limited by Cronometer.
        # Both calls are GET/history operations; no write RPCs are invoked.
        all_history = client.get_user_fasts()
        print(f"Web GWT getUserFasts: record_count={len(all_history)}")
        ranged = client.get_user_fasts_for_range(date(2026, 10, 20), date(2026, 11, 1))
        print(f"Web GWT getUserFastsForRange: record_count={len(ranged)}")
        for name, records in (("all", all_history), ("ranged", ranged)):
            if not isinstance(records, list):
                raise ValueError("Unexpected fasting data response")
            # Field names and formats are safe; personal fasting values are not printed.
            shapes = {}
            for item in records[:20]:
                for key,value in item.items():
                    shape = ("string:length="+str(len(value)) if isinstance(value,str) else type(value).__name__)
                    shapes.setdefault(key,set()).add(shape)
            printable={key:sorted(vals) for key,vals in shapes.items()}
            print(f"{name}: fields_and_formats={printable}")
        print("Probe complete; no health records exported or changed.")
    except Exception as exc:
        # Never print upstream error bodies; they could include account identifiers.
        print(f"Web GWT probe failed: exception_class={type(exc).__name__}")
        sys.exit(2)

if __name__=="__main__":
    main()
