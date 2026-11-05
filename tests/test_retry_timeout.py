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

    def test_transient_failure_then_success_stops_retry(self):
        func = self._func([requests.Timeout("first"), "ok"])
        with patch.object(m.time, "sleep", lambda delay: None):
            result = m._retryable_call(func, max_retries=3)
        self.assertEqual(result, "ok")
        self.assertEqual(func.call_count, 2)


if __name__ == "__main__":
    unittest.main()
