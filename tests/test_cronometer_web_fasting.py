"""Fictional-only tests for strict Cronometer GWT decoding and import validation."""
import importlib.util
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

P = Path(__file__).resolve().parents[1]/"scripts"/"22_sync_cronometer_web_fasts.py"
spec=importlib.util.spec_from_file_location("fast_sync",P)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class TestGwtDecoding(unittest.TestCase):
    def test_known_gwt_long(self):
        timestamp=module.decode_gwt_long("aF_OTzg")
        self.assertEqual(timestamp,datetime(2026,10,27,21,17,tzinfo=timezone.utc))

    def test_invalid_alphabet(self):
        with self.assertRaises(ValueError):
            module.decode_gwt_long("bad!???")

    def test_missing_end_is_null(self):
        self.assertIsNone(module.decode_gwt_long("0"))

    def test_valid_completed_fast(self):
        rows=module.normalize([{"fast_id":12345,"start_ts":"aF_OTzg",
                                "end_ts":"aGCWH5A","is_active":False,"name":"Test"}])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][0],"12345")
        self.assertEqual((rows[0][2]-rows[0][1]),timedelta(hours=14,minutes=33))

    def test_reject_empty(self):
        with self.assertRaises(ValueError):
            module.normalize([])

    def test_reject_duplicate(self):
        item={"fast_id":12345,"start_ts":"aF_OTzg","end_ts":"aGCWH5A","is_active":False}
        with self.assertRaises(ValueError):
            module.normalize([item,item])

    def test_reject_implausible_timestamp(self):
        with self.assertRaises(ValueError):
            module.decode_gwt_long("AAAAAAA")

    def test_reject_completed_without_end(self):
        with self.assertRaises(ValueError):
            module.normalize([{"fast_id":1,"start_ts":"aF_OTzg","end_ts":"","is_active":False}])

if __name__=="__main__":
    unittest.main()
