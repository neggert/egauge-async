"""Mock HTTP clients for JSON API tests."""

import base64
import json
import time
from dataclasses import dataclass
from typing import Any


def create_egauge_jwt(lifetime_seconds: int = 600) -> str:
    """Create a test JWT token with eGauge's beg/ltm format.

    Args:
        lifetime_seconds: Token lifetime in seconds (default: 600 = 10 minutes)

    Returns:
        A JWT token string with header.payload.signature format
    """
    now = time.time()
    payload = {
        "rlm": "eGauge Administration",
        "usr": "readonly",
        "prv": 0,
        "beg": int(now),
        "ltm": lifetime_seconds,
        "gen": 0,
    }
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    return f"header.{payload_encoded}.signature"


class MockAuthManager:
    """Mock JWT authentication manager that returns a fixed token."""

    def __init__(self, token: str = "mock_jwt_token"):
        self.token = token
        self.get_token_calls = 0
        self.logout_calls = 0
        self.invalidate_token_calls = 0

    async def get_token(self) -> str:
        """Return mock JWT token."""
        self.get_token_calls += 1
        return self.token

    async def invalidate_token(self) -> None:
        """Mock invalidate_token - tracks calls."""
        self.invalidate_token_calls += 1

    async def logout(self) -> None:
        """Mock logout - tracks calls."""
        self.logout_calls += 1


@dataclass
class MockResponse:
    """Mock HTTP response."""

    text: str
    status_code: int

    def json(self) -> dict[str, Any]:
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        """Raise an exception for HTTP error status codes."""
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class MockAsyncClient:
    """Mock HTTP client that expects specific URLs and returns canned responses."""

    def __init__(
        self, expected_url: str, response_json: dict[str, Any], status_code: int = 200
    ):
        self.expected_url = expected_url
        self.response_json = response_json
        self.status_code = status_code
        self.calls: list[tuple[str, str, Any]] = []

    async def get(self, url: str, **kwargs: Any) -> MockResponse:
        self.calls.append(("GET", url, None))
        assert url == self.expected_url, f"Expected URL {self.expected_url}, got {url}"
        return MockResponse(json.dumps(self.response_json), self.status_code)

    async def post(self, url: str, **kwargs: Any) -> MockResponse:
        json_data = kwargs.get("json")
        self.calls.append(("POST", url, json_data))
        assert url == self.expected_url, f"Expected URL {self.expected_url}, got {url}"
        return MockResponse(json.dumps(self.response_json), self.status_code)


class MultiResponseClient:
    """Mock HTTP client that returns different responses based on URL patterns."""

    def __init__(self):
        self.calls: list[tuple[str, ...]] = []
        self._get_handlers: dict[str, tuple[dict[str, Any], int]] = {}
        self._post_handlers: dict[str, tuple[dict[str, Any], int]] = {}

    def add_get_handler(
        self, url_pattern: str, response_json: dict[str, Any], status_code: int = 200
    ) -> None:
        """Add a handler for GET requests matching the URL pattern."""
        self._get_handlers[url_pattern] = (response_json, status_code)

    def add_post_handler(
        self, url_pattern: str, response_json: dict[str, Any], status_code: int = 200
    ) -> None:
        """Add a handler for POST requests matching the URL pattern."""
        self._post_handlers[url_pattern] = (response_json, status_code)

    async def get(self, url: str, **kwargs: Any) -> MockResponse:
        params = kwargs.get("params")
        self.calls.append(("GET", url, params))

        for pattern, (response_json, status_code) in self._get_handlers.items():
            if pattern in url:
                return MockResponse(json.dumps(response_json), status_code)

        raise ValueError(f"Unexpected GET: {url}")

    async def post(self, url: str, **kwargs: Any) -> MockResponse:
        json_data = kwargs.get("json")
        self.calls.append(("POST", url, json_data))

        for pattern, (response_json, status_code) in self._post_handlers.items():
            if pattern in url:
                return MockResponse(json.dumps(response_json), status_code)

        raise ValueError(f"Unexpected POST: {url}")


class NeverCalledClient:
    """Mock client that raises an error if any method is called."""

    def __init__(self, error_message: str = "Should not be called"):
        self.error_message = error_message

    async def get(self, url: str, **kwargs: Any) -> MockResponse:
        raise AssertionError(self.error_message)

    async def post(self, url: str, **kwargs: Any) -> MockResponse:
        raise AssertionError(self.error_message)
