"""Mock HTTP clients for JSON API tests."""

import json
from dataclasses import dataclass


class MockAuthManager:
    """Mock JWT authentication manager that returns a fixed token."""

    def __init__(self, token: str = "mock_jwt_token"):
        self.token = token
        self.get_token_calls = 0

    async def get_token(self) -> str:
        """Return mock JWT token."""
        self.get_token_calls += 1
        return self.token

    async def logout(self) -> None:
        """Mock logout (no-op)."""
        pass


@dataclass
class MockResponse:
    """Mock HTTP response."""

    text: str
    status_code: int

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        """Raise an exception for HTTP error status codes."""
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class MockAsyncClient:
    """Mock HTTP client that expects specific URLs and returns canned responses."""

    def __init__(self, expected_url: str, response_json: dict, status_code: int = 200):
        self.expected_url = expected_url
        self.response_json = response_json
        self.status_code = status_code
        self.calls = []

    async def get(self, url: str, **kwargs):
        self.calls.append(("GET", url, None))
        assert url == self.expected_url, f"Expected URL {self.expected_url}, got {url}"
        return MockResponse(json.dumps(self.response_json), self.status_code)

    async def post(self, url: str, **kwargs):
        json_data = kwargs.get("json")
        self.calls.append(("POST", url, json_data))
        assert url == self.expected_url, f"Expected URL {self.expected_url}, got {url}"
        return MockResponse(json.dumps(self.response_json), self.status_code)


class MultiResponseClient:
    """Mock HTTP client that returns different responses based on URL patterns."""

    def __init__(self):
        self.calls = []
        self._get_handlers = {}
        self._post_handlers = {}

    def add_get_handler(
        self, url_pattern: str, response_json: dict, status_code: int = 200
    ):
        """Add a handler for GET requests matching the URL pattern."""
        self._get_handlers[url_pattern] = (response_json, status_code)

    def add_post_handler(
        self, url_pattern: str, response_json: dict, status_code: int = 200
    ):
        """Add a handler for POST requests matching the URL pattern."""
        self._post_handlers[url_pattern] = (response_json, status_code)

    async def get(self, url: str, **kwargs):
        self.calls.append(("GET", url))

        for pattern, (response_json, status_code) in self._get_handlers.items():
            if pattern in url:
                return MockResponse(json.dumps(response_json), status_code)

        raise ValueError(f"Unexpected GET: {url}")

    async def post(self, url: str, **kwargs):
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

    async def get(self, url: str, **kwargs):
        raise AssertionError(self.error_message)

    async def post(self, url: str, **kwargs):
        raise AssertionError(self.error_message)
