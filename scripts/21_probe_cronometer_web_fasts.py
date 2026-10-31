"""Read-only Cronometer WEB fasting probe against the user's account.

No fasting records, credentials, cookies or server responses are logged or
persisted. Uses pinned, inspectable community implementation of GWT-RPC.
This is an isolated diagnostic, NOT a production fasting importer.
"""
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
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

        # GWT RPC long primitives use a special 64-character alphabet, not base62.
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789$_"
        def decode_gwt_long(value):
            if not isinstance(value,str) or not value or any(ch not in alphabet for ch in value):
                return None
            result=0
            for ch in value:
                result=result*64+alphabet.index(ch)
            try:
                return datetime.fromtimestamp(result/1000,timezone.utc)
            except (ValueError, OverflowError, OSError):
                return None
        parsed=[]
        for rec in ranged:
            start=decode_gwt_long(rec.get("start_ts"))
            end=decode_gwt_long(rec.get("end_ts"))
            if start and end and start<end and date(2026,10,20)<=start.date()<=date(2026,11,1):
                parsed.append((rec.get("fast_id"),start,end))
        ids=[row[0] for row in parsed]
        print(f"GWT time decode valid={len(parsed)}; unique_id_count={len(set(ids))}")
        tz=ZoneInfo("Europe/Berlin")
        anchors=[
            (datetime(2026,10,27,22,17,tzinfo=tz), datetime(2026,10,28,12,50,tzinfo=tz)),
            (datetime(2026,10,28,16,42,tzinfo=tz), datetime(2026,10,29,17,15,tzinfo=tz)),
            (datetime(2026,10,26,21,12,tzinfo=tz), datetime(2026,10,27,11,33,tzinfo=tz)),
            (datetime(2026,10,31,0,36,tzinfo=tz), datetime(2026,10,31,16,5,tzinfo=tz)),
        ]
        verified=0
        for s,e in anchors:
            if any(abs((actual_s-s.astimezone(timezone.utc)).total_seconds()) <= 300 and
                   abs((actual_e-e.astimezone(timezone.utc)).total_seconds()) <= 300
                   for _,actual_s,actual_e in parsed):
                verified+=1
        print(f"Screenshot anchor comparisons: {verified}/{len(anchors)} pairs within 5 minutes")
        print("Probe complete; no health records exported or changed.")
    except Exception as exc:
        # Never print upstream error bodies; they could include account identifiers.
        print(f"Web GWT probe failed: exception_class={type(exc).__name__}")
        sys.exit(2)

if __name__=="__main__":
    main()
