#!/usr/bin/env python3
"""Regression tests for the AKShare minute interface rename."""

import unittest
from unittest.mock import patch

import fetch_pvc as m


class MinuteInterfaceCompatibilityTests(unittest.TestCase):
    def test_minute_collection_uses_renamed_akshare_interface(self):
        sample = m.pd.DataFrame(
            [{
                "datetime": "2026-11-16 09:00:00",
                "open": 5000.0,
                "high": 5001.0,
                "low": 4999.0,
                "close": 5000.0,
                "volume": 10,
                "hold": 20,
            }]
        )

        with patch.object(m.ak, "futures_zh_min_sina", return_value=sample) as api, \
             patch.object(m, "update_minute_bars", return_value=(1, 100)) as update:
            result = m._run_minute_bars("V0")

        api.assert_called_once_with(symbol="V0", period="1")
        update.assert_called_once_with("V0", sample)
        self.assertTrue(result.ok)
        self.assertEqual(result.outcome, "success")


if __name__ == "__main__":
    unittest.main()
