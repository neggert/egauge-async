"""Tests for JWT token lifecycle management (parsing, expiration, refresh, 401 handling)"""

import asyncio
import base64
import json
import time

import pytest

from egauge_async.exceptions import (
    EgaugeAuthenticationError,
    EgaugeParsingException,
)
from egauge_async.json.auth import JwtAuthManager, _TokenState
from egauge_async.json.client import EgaugeJsonClient
from mocks import MultiResponseClient, MockAsyncClient, create_egauge_jwt


# Test JWT parsing
def test_parse_jwt_expiry_valid_token():
    """Test parsing expiration from a valid JWT"""
    token = create_egauge_jwt(lifetime_seconds=600)
    result = JwtAuthManager._parse_jwt_expiry(token)

    assert result is not None
    expected_expiry = time.time() + 600
    assert abs(result - expected_expiry) < 2  # Allow for timing


def test_parse_jwt_expiry_missing_exp():
    """Test parsing JWT without beg/ltm claims raises exception"""
    payload = {"sub": "owner", "iat": int(time.time())}
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"header.{payload_encoded}.signature"

    with pytest.raises(EgaugeParsingException, match="missing 'beg'"):
        JwtAuthManager._parse_jwt_expiry(token)


def test_parse_jwt_expiry_malformed_token():
    """Test parsing malformed JWT (only 1 segment) raises exception"""
    with pytest.raises(EgaugeParsingException, match="must have at least 2 segments"):
        JwtAuthManager._parse_jwt_expiry("only_one_segment")


def test_parse_jwt_expiry_invalid_base64():
    """Test parsing JWT with invalid base64 raises exception"""
    token = "header.!!!invalid_base64!!!.signature"

    with pytest.raises(EgaugeParsingException, match="Failed to decode JWT payload"):
        JwtAuthManager._parse_jwt_expiry(token)


def test_parse_jwt_expiry_exp_in_past():
    """Test parsing JWT that's already expired raises exception"""
    # Token that expired 10 seconds ago (beg was 610 seconds ago, ltm was 600)
    payload = {"beg": int(time.time() - 610), "ltm": 600}
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"header.{payload_encoded}.signature"

    with pytest.raises(EgaugeParsingException, match="already expired"):
        JwtAuthManager._parse_jwt_expiry(token)


def test_parse_jwt_expiry_with_padding():
    """Test parsing JWT that needs base64 padding"""
    payload = {"beg": int(time.time()), "ltm": 600}
    # Create payload that needs padding (length not multiple of 4)
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"hdr.{payload_encoded}.sig"

    result = JwtAuthManager._parse_jwt_expiry(token)

    assert result is not None
    expected_expiry = time.time() + 600
    assert abs(result - expected_expiry) < 2


# Test token validity checking
def test_is_token_valid_no_token():
    """Test _is_token_valid returns False when no token is set"""
    mock_client = MockAsyncClient("https://egauge.local", {})
    auth = JwtAuthManager("https://egauge.local", "owner", "password", mock_client)

    assert not auth._is_token_valid()


def test_is_token_valid_expired_token():
    """Test _is_token_valid returns False for expired token"""
    mock_client = MockAsyncClient("https://egauge.local", {})
    auth = JwtAuthManager(
        "https://egauge.local",
        "owner",
        "password",
        mock_client,
        refresh_buffer_seconds=60,
    )

    # Set token that expires in 30 seconds (within buffer window)
    auth._token_state = _TokenState(
        token="test_token",
        expiry_timestamp=time.time() + 30,
        issued_at=time.time() - 570,
    )

    assert not auth._is_token_valid()  # Should be invalid (within buffer)


def test_is_token_valid_valid_token():
    """Test _is_token_valid returns True for valid token"""
    mock_client = MockAsyncClient("https://egauge.local", {})
    auth = JwtAuthManager(
        "https://egauge.local",
        "owner",
        "password",
        mock_client,
        refresh_buffer_seconds=60,
    )

    # Set token that expires in 5 minutes (outside buffer window)
    auth._token_state = _TokenState(
        token="test_token",
        expiry_timestamp=time.time() + 300,
        issued_at=time.time(),
    )

    assert auth._is_token_valid()


# Test proactive token refresh
@pytest.mark.asyncio
async def test_get_token_refreshes_near_expiry():
    """Test that get_token() refreshes token when near expiration"""
    new_jwt = create_egauge_jwt(lifetime_seconds=600)

    mock_client = MultiResponseClient()
    mock_client.add_get_handler(
        "/api/auth/unauthorized",
        {"rlm": "eGauge", "nnc": "nonce123", "error": "Auth required"},
        status_code=401,
    )
    mock_client.add_post_handler("/api/auth/login", {"jwt": new_jwt})

    auth = JwtAuthManager(
        "https://egauge.local",
        "owner",
        "password",
        mock_client,
        refresh_buffer_seconds=60,
    )

    # Set token that expires in 30 seconds (within buffer)
    auth._token_state = _TokenState(
        token="old_token_123",
        expiry_timestamp=time.time() + 30,
        issued_at=time.time() - 570,
    )

    token = await auth.get_token()

    # Should have refreshed to new token
    assert token == new_jwt
    assert auth._token_state.token == new_jwt


@pytest.mark.asyncio
async def test_get_token_no_refresh_when_valid():
    """Test that get_token() doesn't refresh when token is still valid"""
    mock_client = MultiResponseClient()
    # No handlers - should never be called

    auth = JwtAuthManager(
        "https://egauge.local",
        "owner",
        "password",
        mock_client,
        refresh_buffer_seconds=60,
    )

    # Set token that expires in 5 minutes (well outside buffer)
    auth._token_state = _TokenState(
        token="valid_token",
        expiry_timestamp=time.time() + 300,
        issued_at=time.time(),
    )

    token = await auth.get_token()

    # Should return cached token without any API calls
    assert token == "valid_token"
    assert len(mock_client.calls) == 0


# Test concurrent token refresh
@pytest.mark.asyncio
async def test_concurrent_get_token_single_refresh():
    """Test that concurrent get_token() calls trigger only one refresh"""
    refreshed_jwt = create_egauge_jwt(lifetime_seconds=600)

    mock_client = MultiResponseClient()
    mock_client.add_get_handler(
        "/api/auth/unauthorized",
        {"rlm": "eGauge", "nnc": "nonce", "error": "Auth required"},
        status_code=401,
    )
    mock_client.add_post_handler("/api/auth/login", {"jwt": refreshed_jwt})

    auth = JwtAuthManager(
        "https://egauge.local",
        "owner",
        "password",
        mock_client,
        refresh_buffer_seconds=60,
    )

    # Set expired token
    auth._token_state = _TokenState(
        token="expired",
        expiry_timestamp=time.time() - 10,
        issued_at=time.time() - 610,
    )

    # Make 10 concurrent calls
    tokens = await asyncio.gather(*[auth.get_token() for _ in range(10)])

    # All should receive the same new token
    assert all(t == refreshed_jwt for t in tokens)

    # Should have made only 1 authentication (1 nonce fetch + 1 login)
    assert len(mock_client.calls) == 2
    assert mock_client.calls[0][0] == "GET"  # nonce
    assert mock_client.calls[1][0] == "POST"  # login


# Test invalidate_token
@pytest.mark.asyncio
async def test_invalidate_token_clears_state():
    """Test that invalidate_token() clears token state"""
    mock_client = MockAsyncClient("https://egauge.local", {})
    auth = JwtAuthManager("https://egauge.local", "owner", "password", mock_client)

    # Set token
    auth._token_state = _TokenState(
        token="test_token",
        expiry_timestamp=time.time() + 600,
        issued_at=time.time(),
    )

    await auth.invalidate_token()

    assert auth._token_state is None


@pytest.mark.asyncio
async def test_invalidate_token_when_no_token():
    """Test that invalidate_token() is safe when no token is set"""
    mock_client = MockAsyncClient("https://egauge.local", {})
    auth = JwtAuthManager("https://egauge.local", "owner", "password", mock_client)

    # Should not raise any errors
    await auth.invalidate_token()

    assert auth._token_state is None


# Test 401 handling in client
@pytest.mark.asyncio
async def test_client_401_triggers_refresh_and_retry():
    """Test that 401 response triggers token refresh and request retry"""
    import json as json_module
    from mocks import MockResponse

    register_call_count = 0

    async def get_handler(url, **kwargs):
        """Mock handler that handles /register and auth endpoints"""
        nonlocal register_call_count

        # Handle auth endpoints
        if "/api/auth/unauthorized" in url:
            return MockResponse(
                json_module.dumps(
                    {"rlm": "eGauge", "nnc": "nonce", "error": "Auth required"}
                ),
                401,
            )

        # Handle register endpoint
        if "/api/register" in url:
            register_call_count += 1
            if register_call_count == 1:
                # First call: return 401
                return MockResponse(
                    json_module.dumps(
                        {"rlm": "eGauge", "nnc": "nonce", "error": "Token expired"}
                    ),
                    401,
                )
            else:
                # Second call (after refresh): return success
                return MockResponse(json_module.dumps({"registers": []}), 200)

        raise ValueError(f"Unexpected URL: {url}")

    new_jwt = create_egauge_jwt(lifetime_seconds=600)

    mock_client = MultiResponseClient()
    mock_client.get = get_handler
    mock_client.add_post_handler("/api/auth/login", {"jwt": new_jwt})

    auth = JwtAuthManager("https://egauge.local", "owner", "password", mock_client)

    # Set initial valid token
    auth._token_state = _TokenState(
        token="old_token",
        expiry_timestamp=time.time() + 300,
        issued_at=time.time(),
    )

    client = EgaugeJsonClient(
        "https://egauge.local", "owner", "password", mock_client, auth
    )

    # Make request - should succeed after retry
    response = await client._get_with_auth("https://egauge.local/api/register")

    assert response.status_code == 200
    assert register_call_count == 2  # Initial request + retry


@pytest.mark.asyncio
async def test_client_double_401_raises_error():
    """Test that double 401 (after refresh) raises authentication error"""
    import json as json_module
    from mocks import MockResponse

    # Create a handler that returns nonce but login fails with 401
    async def handler_with_failed_login(url, **kwargs):
        """Mock handler that provides nonce but fails login"""
        if "/api/auth/unauthorized" in url:
            # Return proper nonce response with 401
            return MockResponse(
                json_module.dumps(
                    {"rlm": "eGauge", "nnc": "nonce", "error": "Auth required"}
                ),
                401,
            )
        # For any other request (including /register), return 401 error
        return MockResponse(json_module.dumps({"error": "Invalid credentials"}), 401)

    async def failed_post_handler(url, **kwargs):
        """Mock POST handler that always fails with 400 for invalid credentials"""
        return MockResponse(json_module.dumps({"error": "Invalid credentials"}), 400)

    mock_client = MultiResponseClient()
    # Override get to handle nonce and register requests
    mock_client.get = handler_with_failed_login
    # Override post to fail login attempts
    mock_client.post = failed_post_handler

    auth = JwtAuthManager("https://egauge.local", "owner", "password", mock_client)

    # Set initial token
    auth._token_state = _TokenState(
        token="token",
        expiry_timestamp=time.time() + 300,
        issued_at=time.time(),
    )

    client = EgaugeJsonClient(
        "https://egauge.local", "owner", "password", mock_client, auth
    )

    # Should raise after second 401
    # The error will be different since both the request AND the refresh will get 401
    with pytest.raises(EgaugeAuthenticationError):
        await client._get_with_auth("https://egauge.local/api/register")


# Test JWT parsing failure raises exception
@pytest.mark.asyncio
async def test_authentication_fails_with_invalid_jwt():
    """Test that authentication raises exception when JWT parsing fails"""
    mock_client = MultiResponseClient()
    mock_client.add_get_handler(
        "/api/auth/unauthorized",
        {"rlm": "eGauge", "nnc": "nonce", "error": "Auth required"},
        status_code=401,
    )
    # Return a JWT with invalid base64 payload
    mock_client.add_post_handler(
        "/api/auth/login", {"jwt": "header.!!!invalid!!.signature"}
    )

    auth = JwtAuthManager("https://egauge.local", "owner", "password", mock_client)

    # Should raise EgaugeParsingException from JWT parsing (not auth error)
    with pytest.raises(EgaugeParsingException, match="Failed to decode JWT payload"):
        await auth.get_token()


# Test configurable refresh buffer
def test_refresh_buffer_validation():
    """Test that invalid refresh_buffer_seconds raises ValueError"""
    mock_client = MockAsyncClient("https://egauge.local", {})

    # Test negative buffer
    with pytest.raises(ValueError, match="must be between 1 and 600"):
        JwtAuthManager(
            "https://egauge.local",
            "owner",
            "password",
            mock_client,
            refresh_buffer_seconds=-1,
        )

    # Test zero buffer
    with pytest.raises(ValueError, match="must be between 1 and 600"):
        JwtAuthManager(
            "https://egauge.local",
            "owner",
            "password",
            mock_client,
            refresh_buffer_seconds=0,
        )

    # Test buffer too large
    with pytest.raises(ValueError, match="must be between 1 and 600"):
        JwtAuthManager(
            "https://egauge.local",
            "owner",
            "password",
            mock_client,
            refresh_buffer_seconds=700,
        )


def test_custom_refresh_buffer():
    """Test that custom refresh buffer is respected"""
    mock_client = MockAsyncClient("https://egauge.local", {})
    auth = JwtAuthManager(
        "https://egauge.local",
        "owner",
        "password",
        mock_client,
        refresh_buffer_seconds=120,
    )

    # Set token that expires in 90 seconds
    auth._token_state = _TokenState(
        token="token",
        expiry_timestamp=time.time() + 90,
        issued_at=time.time(),
    )

    # With 120s buffer, this should be invalid
    assert not auth._is_token_valid()

    # Set token that expires in 150 seconds
    auth._token_state = _TokenState(
        token="token",
        expiry_timestamp=time.time() + 150,
        issued_at=time.time(),
    )

    # With 120s buffer, this should be valid
    assert auth._is_token_valid()
