#!/usr/bin/env python3
"""Stage 3 tests for JSONL concurrent append safety.

All tests use temporary directories only (no real network or formal data files).
Concurrency is synchronized with barriers/events, not fixed sleeps.
"""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

import fetch_pvc as m


class AppendJsonlConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = self.dir / "minute_data_quality.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def _read_records(self):
        if not self.log.exists():
            return []
        with self.log.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_empty_records_no_op(self):
        self.assertEqual(m.append_jsonl([], log_path=self.log), 0)
        self.assertFalse(self.log.exists())

    def test_single_thread_write(self):
        records = [{"symbol": "V0", "datetime": "2026-10-28 09:00:00"}]
        self.assertEqual(m.append_jsonl(records, log_path=self.log), 1)
        rows = self._read_records()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "V0")

    def test_duplicate_records_deduplicated(self):
        record = {"symbol": "V0", "datetime": "2026-10-28 09:00:00"}
        self.assertEqual(m.append_jsonl([record], log_path=self.log), 1)
        self.assertEqual(m.append_jsonl([dict(record)], log_path=self.log), 0)
        rows = self._read_records()
        self.assertEqual(len(rows), 1)

    def test_two_threads_disjoint_records(self):
        barrier = threading.Barrier(2)

        def worker(symbol):
            barrier.wait()
            m.append_jsonl(
                [{"symbol": symbol, "datetime": "2026-10-28 09:00:00"}],
                log_path=self.log,
            )

        t1 = threading.Thread(target=worker, args=("V0",))
        t2 = threading.Thread(target=worker, args=("TA0",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        rows = self._read_records()
        symbols = sorted(r["symbol"] for r in rows)
        self.assertEqual(symbols, ["TA0", "V0"])
        raw_lines = self.log.read_text(encoding="utf-8").splitlines()
        for line in raw_lines:
            json.loads(line)

    def test_two_threads_overlapping_records_deduplicated(self):
        barrier = threading.Barrier(2)
        record = {"symbol": "V0", "datetime": "2026-10-28 09:00:00"}

        def worker():
            barrier.wait()
            m.append_jsonl([dict(record)], log_path=self.log)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        rows = self._read_records()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "V0")

    def test_write_failure_preserves_original_and_cleans_temp(self):
        original = '{"symbol":"V0","datetime":"2026-10-28 09:00:00"}\n'
        self.log.write_text(original, encoding="utf-8")
        tmp = self.dir / "minute_data_quality.jsonl.tmp"
        tmp.mkdir()
        try:
            with self.assertRaises(Exception):
                m.append_jsonl(
                    [{"symbol": "V0", "datetime": "2026-10-28 09:01:00"}],
                    log_path=self.log,
                )
        finally:
            if tmp.is_dir():
                tmp.rmdir()
        self.assertEqual(self.log.read_text(encoding="utf-8"), original)
        self.assertFalse(tmp.exists())

    def test_different_paths_write_independently(self):
        log_a = self.dir / "a.jsonl"
        log_b = self.dir / "b.jsonl"
        started = threading.Event()

        def worker_a():
            started.wait(timeout=5)
            m.append_jsonl(
                [{"symbol": "A", "datetime": "2026-10-28 09:00:00"}],
                log_path=log_a,
            )

        def worker_b():
            m.append_jsonl(
                [{"symbol": "B", "datetime": "2026-10-28 09:00:00"}],
                log_path=log_b,
            )
            started.set()

        t1 = threading.Thread(target=worker_a)
        t2 = threading.Thread(target=worker_b)
        t1.start()
        t2.start()
        t2.join(timeout=5)
        t1.join(timeout=5)

        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())
        self.assertEqual(
            [json.loads(line) for line in log_a.read_text(encoding="utf-8").splitlines() if line.strip()][0]["symbol"],
            "A",
        )
        self.assertEqual(
            [json.loads(line) for line in log_b.read_text(encoding="utf-8").splitlines() if line.strip()][0]["symbol"],
            "B",
        )

    def test_same_path_returns_distinct_lock_objects(self):
        lock_a = m._get_jsonl_lock(self.log)
        lock_b = m._get_jsonl_lock(self.log)
        self.assertIs(lock_a, lock_b)
        other = m._get_jsonl_lock(self.dir / "other.jsonl")
        self.assertIsNot(lock_a, other)


if __name__ == "__main__":
    unittest.main()
