#!/usr/bin/env python3
"""Stage 2 tests for HTTP timeout injection and retryable exception classification.

All tests use mocks only (no real network). Each test restores global requests state.
"""
import unittest
from unittest.mock import Mock, patch

import requests

import fetch_pvc as m


def _http_error(status_code, message=None):
    exc = requests.HTTPError(message or f"HTTP {status_code}")
    exc.response = Mock(status_code=status_code)
    return exc


class TimeoutInjectionTests(unittest.TestCase):
    def setUp(self):
        self._saved_get = requests.get
        self._saved_api_get = requests.api.get
        self._saved_original = m._original_requests_get

    def tearDown(self):
        requests.get = self._saved_get
        requests.api.get = self._saved_api_get
        m._original_requests_get = self._saved_original
        m.requests.get = self._saved_get
        m.requests.api.get = self._saved_api_get

    def _ok_response(self):
        response = Mock()
        response.raise_for_status = Mock()
        return response

    def test_no_timeout_receives_connect_read_timeout(self):
        mock_get = Mock(return_value=self._ok_response())
        with patch.object(m, "_original_requests_get", mock_get):
            m._requests_get_with_timeout("http://example.com")
        self.assertEqual(mock_get.call_args.kwargs["timeout"], (10, 30))

    def test_none_timeout_receives_connect_read_timeout(self):
        mock_get = Mock(return_value=self._ok_response())
        with patch.object(m, "_original_requests_get", mock_get):
            m._requests_get_with_timeout("http://example.com", timeout=None)
        self.assertEqual(mock_get.call_args.kwargs["timeout"], (10, 30))

    def test_explicit_timeout_is_preserved(self):
        mock_get = Mock(return_value=self._ok_response())
        with patch.object(m, "_original_requests_get", mock_get):
            m._requests_get_with_timeout("http://example.com", timeout=99)
        self.assertEqual(mock_get.call_args.kwargs["timeout"], 99)

    def test_raise_for_status_is_called(self):
        response = self._ok_response()
        mock_get = Mock(return_value=response)
        with patch.object(m, "_original_requests_get", mock_get):
            result = m._requests_get_with_timeout("http://example.com")
        self.assertIs(result, response)
        response.raise_for_status.assert_called_once_with()

    def test_global_requests_state_restored(self):
        mock_get = Mock(return_value=self._ok_response())
        with patch.object(m, "_original_requests_get", mock_get):
            m._requests_get_with_timeout("http://example.com")
        self.assertIs(requests.get, self._saved_get)
        self.assertIs(requests.api.get, self._saved_api_get)
        self.assertIs(m._original_requests_get, self._saved_original)


class RetryClassificationTests(unittest.TestCase):
    def setUp(self):
        self._saved_get = requests.get
        self._saved_api_get = requests.api.get
        self._saved_original = m._original_requests_get

    def tearDown(self):
        requests.get = self._saved_get
        requests.api.get = self._saved_api_get
        m._original_requests_get = self._saved_original
        m.requests.get = self._saved_get
        m.requests.api.get = self._saved_api_get

    def _func(self, side_effect):
        func = Mock(side_effect=side_effect)
        func.__name__ = "mock_func"
        return func

    def test_requests_timeout_is_retried(self):
        func = self._func(requests.Timeout("timeout boom"))
        with self.assertRaises(requests.Timeout):
            m._retryable_call(func, max_retries=3)
        self.assertEqual(func.call_count, 3)

    def test_requests_connection_error_is_retried(self):
        func = self._func(requests.ConnectionError("connection boom"))
        with self.assertRaises(requests.ConnectionError):
            m._retryable_call(func, max_retries=3)
        self.assertEqual(func.call_count, 3)

    def test_http_429_is_retried(self):
        func = self._func(_http_error(429, "too many"))
        with self.assertRaises(requests.HTTPError):
            m._retryable_call(func, max_retries=3)
        self.assertEqual(func.call_count, 3)

    def test_http_5xx_are_retried(self):
        for status in (500, 502, 503, 504):
            func = self._func(_http_error(status, f"server {status}"))
            with self.subTest(status=status):
                with self.assertRaises(requests.HTTPError):
                    m._retryable_call(func, max_retries=3)
                self.assertEqual(func.call_count, 3)

    def test_http_4xx_are_not_retried(self):
        for status in (400, 401, 403, 404):
            func = self._func(_http_error(status, f"client {status}"))
            with self.subTest(status=status):
                with self.assertRaises(requests.HTTPError):
                    m._retryable_call(func, max_retries=3)
                self.assertEqual(func.call_count, 1)

    def test_other_http_status_is_not_retried(self):
        func = self._func(_http_error(418, "teapot"))
        with self.assertRaises(requests.HTTPError):
            m._retryable_call(func, max_retries=3)
        self.assertEqual(func.call_count, 1)

    def test_value_error_is_not_retried(self):
        func = self._func(ValueError("bad data"))
        with self.assertRaises(ValueError):
            m._retryable_call(func, max_retries=3)
        self.assertEqual(func.call_count, 1)

    def test_runtime_error_is_not_retried(self):
        func = self._func(RuntimeError("empty"))
        with self.assertRaises(RuntimeError):
            m._retryable_call(func, max_retries=3)
        self.assertEqual(func.call_count, 1)

    def test_retry_exhaustion_preserves_exception(self):
        func = self._func(requests.Timeout("original timeout message"))
        with self.assertRaises(requests.Timeout) as cm:
            m._retryable_call(func, max_retries=3)
        self.assertEqual(type(cm.exception), requests.Timeout)
        self.assertEqual(str(cm.exception), "original timeout message")

    def test_retry_exhaustion_preserves_connection_error(self):
        func = self._func(requests.ConnectionError("original connection message"))
        with self.assertRaises(requests.ConnectionError) as cm:
            m._retryable_call(func, max_retries=3)
        self.assertEqual(type(cm.exception), requests.ConnectionError)
        self.assertEqual(str(cm.exception), "original connection message")
        self.assertEqual(func.call_count, 3)

    def test_retry_exhaustion_preserves_http_error(self):
        exc = _http_error(503, "original http 503 message")
        func = self._func(exc)
        with self.assertRaises(requests.HTTPError) as cm:
            m._retryable_call(func, max_retries=3)
        self.assertIs(cm.exception, exc)
        self.assertEqual(type(cm.exception), requests.HTTPError)
        self.assertEqual(str(cm.exception), "original http 503 message")
        self.assertEqual(func.call_count, 3)

    def test_http_400_is_not_retried(self):
        func = self._func(_http_error(400, "bad request"))
        with self.assertRaises(requests.HTTPError):
            m._retryable_call(func, max_retries=3)
        self.assertEqual(func.call_count, 1)

    def test_http_401_is_not_retried(self):
        func = self._func(_http_error(401, "unauthorized"))
        with self.assertRaises(requests.HTTPError):
            m._retryable_call(func, max_retries=3)
        self.assertEqual(func.call_count, 1)

    def test_http_403_is_not_retried(self):
        func = self._func(_http_error(403, "forbidden"))
        with self.assertRaises(requests.HTTPError):
            m._retryable_call(func, max_retries=3)
        self.assertEqual(func.call_count, 1)

    def test_http_404_is_not_retried(self):
        func = self._func(_http_error(404, "not found"))
        with self.assertRaises(requests.HTTPError):
            m._retryable_call(func, max_retries=3)
        self.assertEqual(func.call_count, 1)

    def test_transient_failure_then_success_stops_retry(self):
        func = self._func([requests.Timeout("first"), "ok"])
        with patch.object(m.time, "sleep", lambda delay: None):
            result = m._retryable_call(func, max_retries=3)
        self.assertEqual(result, "ok")
        self.assertEqual(func.call_count, 2)


class PatchedRequestsGetChainTests(unittest.TestCase):
    """Full chain: _retryable_call -> requests.get -> _requests_get_with_timeout -> _original_requests_get -> raise_for_status."""

    def setUp(self):
        self._saved_get = requests.get
        self._saved_api_get = requests.api.get
        self._saved_original = m._original_requests_get

    def tearDown(self):
        requests.get = self._saved_get
        requests.api.get = self._saved_api_get
        m._original_requests_get = self._saved_original
        m.requests.get = self._saved_get
        m.requests.api.get = self._saved_api_get

    def _ok_response(self):
        response = Mock()
        response.raise_for_status = Mock()
        return response

    def _http_error(self, status, message=None):
        exc = requests.HTTPError(message or f"HTTP {status}")
        exc.response = Mock(status_code=status)
        return exc

    def test_http_503_then_success_retries_via_requests_get(self):
        ok = self._ok_response()
        mock_original = Mock(side_effect=[self._http_error(503, "retry503"), ok])
        with patch.object(m.time, "sleep", lambda delay: None), \
             patch.object(m, "_original_requests_get", mock_original):
            result = m._retryable_call(requests.get, 3, 0.01, 0.01, "http://example.com")
        self.assertEqual(mock_original.call_count, 2)
        self.assertIs(result, ok)
        self.assertEqual(mock_original.call_args_list[0][1]["timeout"], (10, 30))

    def test_http_400_not_retried_via_requests_get(self):
        exc = self._http_error(400, "bad400")
        with patch.object(m.time, "sleep", lambda delay: None):
            mock_original = Mock(side_effect=exc)
            with patch.object(m, "_original_requests_get", mock_original):
                with self.assertRaises(requests.HTTPError) as cm:
                    m._retryable_call(requests.get, 3, 0.01, 0.01, "http://example.com")
            self.assertIs(cm.exception, exc)
            self.assertEqual(mock_original.call_count, 1)

    def test_timeout_then_success_retries_via_requests_get(self):
        with patch.object(m.time, "sleep", lambda delay: None):
            mock_original = Mock(side_effect=[requests.Timeout("tmo"), self._ok_response()])
            with patch.object(m, "_original_requests_get", mock_original):
                result = m._retryable_call(requests.get, 3, 0.01, 0.01, "http://example.com")
            self.assertEqual(mock_original.call_count, 2)
            self.assertIsNotNone(result)

    def test_connection_error_then_success_retries_via_requests_get(self):
        with patch.object(m.time, "sleep", lambda delay: None):
            mock_original = Mock(side_effect=[requests.ConnectionError("conn"), self._ok_response()])
            with patch.object(m, "_original_requests_get", mock_original):
                result = m._retryable_call(requests.get, 3, 0.01, 0.01, "http://example.com")
            self.assertEqual(mock_original.call_count, 2)
            self.assertIsNotNone(result)

    def test_global_state_restored_after_chain(self):
        saved_get = requests.get
        saved_api = requests.api.get
        saved_orig = m._original_requests_get
        mock_original = Mock(return_value=self._ok_response())
        with patch.object(m, "_original_requests_get", mock_original):
            m._retryable_call(requests.get, 3, 0.01, 0.01, "http://example.com")
        self.assertIs(requests.get, saved_get)
        self.assertIs(requests.api.get, saved_api)
        self.assertIs(m._original_requests_get, saved_orig)

    def test_no_recursion_wrapper_is_not_original(self):
        self.assertIsNot(m._original_requests_get, m._requests_get_with_timeout)
        self.assertIs(requests.get, m._requests_get_with_timeout)
        mock_original = Mock(return_value=self._ok_response())
        with patch.object(m, "_original_requests_get", mock_original):
            result = m._requests_get_with_timeout("http://example.com")
        self.assertEqual(mock_original.call_count, 1)
        self.assertIsNotNone(result)


class RunCollectionCompatibilityTests(unittest.TestCase):
    """Stage 1 compatibility: run_collection still collects failures and returns 1.

    Mock only (no network/files); global requests state is restored afterwards.
    """

    def setUp(self):
        self._saved_get = requests.get
        self._saved_api_get = requests.api.get
        self._saved_original = m._original_requests_get

    def tearDown(self):
        requests.get = self._saved_get
        requests.api.get = self._saved_api_get
        m._original_requests_get = self._saved_original
        m.requests.get = self._saved_get
        m.requests.api.get = self._saved_api_get

    def test_run_collection_failure_returns_one(self):
        with patch.object(m, "_run_minute_bars", return_value=m.TaskResult("minute", "V0", "success")), \
             patch.object(m, "_run_daily_bars", return_value=m.TaskResult("daily", "V0", "failed", "RuntimeError", "daily boom")):
            self.assertEqual(m.run_collection(["V0"]), 1)

    def test_run_collection_success_returns_zero(self):
        with patch.object(m, "_run_minute_bars", return_value=m.TaskResult("minute", "V0", "success")), \
             patch.object(m, "_run_daily_bars", return_value=m.TaskResult("daily", "V0", "success")):
            self.assertEqual(m.run_collection(["V0"]), 0)


if __name__ == "__main__":
    unittest.main()
