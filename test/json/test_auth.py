import base64
import hashlib
import json
import time

import pytest

from egauge_async.exceptions import EgaugeAuthenticationError
from egauge_async.json.auth import JwtAuthManager, _TokenState
from egauge_async.json.models import NonceResponse
from mocks import (
    MockAsyncClient,
    MultiResponseClient,
    NeverCalledClient,
    create_egauge_jwt,
)


# Test _generate_client_nonce()
def test_generate_client_nonce_returns_32_char_hex():
    """Test that _generate_client_nonce returns a 32-character hex string"""
    nonce = JwtAuthManager._generate_client_nonce()

    assert isinstance(nonce, str)
    assert len(nonce) == 32
    # Verify it's a valid hex string
    int(nonce, 16)


def test_generate_client_nonce_is_unique():
    """Test that _generate_client_nonce generates unique values"""
    nonce1 = JwtAuthManager._generate_client_nonce()
    nonce2 = JwtAuthManager._generate_client_nonce()

    assert nonce1 != nonce2


# Test _calculate_digest_hash()
def test_calculate_digest_hash_with_known_values():
    """Test digest hash calculation with known values from eGauge docs"""
    username = "owner"
    password = "test123"
    realm = "eGauge Administration"
    server_nonce = "test_server_nonce"
    client_nonce = "test_client_nonce"

    # Calculate expected hash
    ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
    expected_hash = hashlib.md5(
        f"{ha1}:{server_nonce}:{client_nonce}".encode()
    ).hexdigest()

    result = JwtAuthManager._calculate_digest_hash(
        username, password, realm, server_nonce, client_nonce
    )

    assert result == expected_hash


def test_calculate_digest_hash_different_inputs():
    """Test that different inputs produce different hashes"""
    hash1 = JwtAuthManager._calculate_digest_hash(
        "user1", "pass1", "realm", "nonce1", "cnonce1"
    )
    hash2 = JwtAuthManager._calculate_digest_hash(
        "user2", "pass1", "realm", "nonce1", "cnonce1"
    )

    assert hash1 != hash2


# Test _parse_jwt_expiry()
def test_parse_jwt_expiry_valid_egauge_token():
    """Test parsing a valid eGauge JWT with beg and ltm fields"""
    token = create_egauge_jwt(lifetime_seconds=600)
    expiry = JwtAuthManager._parse_jwt_expiry(token)

    # Expiry should be approximately 600 seconds from now
    expected_expiry = time.time() + 600
    assert abs(expiry - expected_expiry) < 2  # Allow 2 second tolerance


def test_parse_jwt_expiry_missing_beg():
    """Test that missing 'beg' field raises EgaugeParsingException"""
    from egauge_async.exceptions import EgaugeParsingException

    # Create JWT without 'beg' field
    payload = {"ltm": 600, "usr": "readonly"}
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"header.{payload_encoded}.signature"

    with pytest.raises(
        EgaugeParsingException, match="JWT missing 'beg' \\(begin timestamp\\) claim"
    ):
        JwtAuthManager._parse_jwt_expiry(token)


def test_parse_jwt_expiry_missing_ltm():
    """Test that missing 'ltm' field raises EgaugeParsingException"""
    from egauge_async.exceptions import EgaugeParsingException

    # Create JWT without 'ltm' field
    payload = {"beg": int(time.time()), "usr": "readonly"}
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"header.{payload_encoded}.signature"

    with pytest.raises(
        EgaugeParsingException, match="JWT missing 'ltm' \\(lifetime\\) claim"
    ):
        JwtAuthManager._parse_jwt_expiry(token)


def test_parse_jwt_expiry_invalid_beg_type():
    """Test that non-numeric 'beg' field raises EgaugeParsingException"""
    from egauge_async.exceptions import EgaugeParsingException

    payload = {"beg": "not_a_number", "ltm": 600}
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"header.{payload_encoded}.signature"

    with pytest.raises(
        EgaugeParsingException,
        match="JWT 'beg' claim must be numeric, got invalid string",
    ):
        JwtAuthManager._parse_jwt_expiry(token)


def test_parse_jwt_expiry_invalid_ltm_type():
    """Test that non-numeric 'ltm' field raises EgaugeParsingException"""
    from egauge_async.exceptions import EgaugeParsingException

    payload = {"beg": int(time.time()), "ltm": "not_a_number"}
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"header.{payload_encoded}.signature"

    with pytest.raises(
        EgaugeParsingException,
        match="JWT 'ltm' claim must be numeric, got invalid string",
    ):
        JwtAuthManager._parse_jwt_expiry(token)


def test_parse_jwt_expiry_negative_lifetime():
    """Test that negative lifetime raises EgaugeParsingException"""
    from egauge_async.exceptions import EgaugeParsingException

    payload = {"beg": int(time.time()), "ltm": -100}
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"header.{payload_encoded}.signature"

    with pytest.raises(
        EgaugeParsingException, match="JWT 'ltm' \\(lifetime\\) must be positive"
    ):
        JwtAuthManager._parse_jwt_expiry(token)


def test_parse_jwt_expiry_zero_lifetime():
    """Test that zero lifetime raises EgaugeParsingException"""
    from egauge_async.exceptions import EgaugeParsingException

    payload = {"beg": int(time.time()), "ltm": 0}
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"header.{payload_encoded}.signature"

    with pytest.raises(
        EgaugeParsingException, match="JWT 'ltm' \\(lifetime\\) must be positive"
    ):
        JwtAuthManager._parse_jwt_expiry(token)


def test_parse_jwt_expiry_excessive_lifetime():
    """Test that lifetime > 24 hours raises EgaugeParsingException"""
    from egauge_async.exceptions import EgaugeParsingException

    payload = {"beg": int(time.time()), "ltm": 86401}  # 24 hours + 1 second
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"header.{payload_encoded}.signature"

    with pytest.raises(
        EgaugeParsingException, match="JWT 'ltm' \\(lifetime\\) is too long"
    ):
        JwtAuthManager._parse_jwt_expiry(token)


def test_parse_jwt_expiry_already_expired():
    """Test that already expired token raises EgaugeParsingException"""
    from egauge_async.exceptions import EgaugeParsingException

    # Token that expired 10 seconds ago
    payload = {"beg": int(time.time() - 610), "ltm": 600}
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"header.{payload_encoded}.signature"

    with pytest.raises(EgaugeParsingException, match="JWT already expired"):
        JwtAuthManager._parse_jwt_expiry(token)


def test_parse_jwt_expiry_malformed_token():
    """Test that malformed JWT raises EgaugeParsingException"""
    from egauge_async.exceptions import EgaugeParsingException

    with pytest.raises(
        EgaugeParsingException,
        match="Malformed JWT: token must have at least 2 segments",
    ):
        JwtAuthManager._parse_jwt_expiry("not_a_valid_token")


def test_parse_jwt_expiry_string_numeric_values():
    """Test that string numeric values are properly converted"""
    # Some implementations might return strings for numeric values
    payload = {"beg": str(int(time.time())), "ltm": "600"}
    payload_encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    token = f"header.{payload_encoded}.signature"

    expiry = JwtAuthManager._parse_jwt_expiry(token)
    expected_expiry = time.time() + 600
    assert abs(expiry - expected_expiry) < 2  # Allow 2 second tolerance


# Test _fetch_nonce()
@pytest.mark.asyncio
async def test_fetch_nonce_success():
    """Test successfully fetching server nonce from /api/auth/unauthorized"""
    response_data = {
        "rlm": "eGauge Administration",
        "nnc": "eyJ0eXAiJkpXVCJ9.eyJzdWIi.w5GCvM",
        "error": "Authentication required.",
    }
    mock_client = MockAsyncClient(
        "https://egauge12345.local/api/auth/unauthorized",
        response_data,
        status_code=401,
    )

    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )
    nonce_response = await handler._fetch_nonce()

    assert nonce_response.realm == "eGauge Administration"
    assert nonce_response.nonce == "eyJ0eXAiJkpXVCJ9.eyJzdWIi.w5GCvM"
    assert nonce_response.error == "Authentication required."
    assert len(mock_client.calls) == 1
    assert mock_client.calls[0][0] == "GET"


@pytest.mark.asyncio
async def test_fetch_nonce_error():
    """Test handling of error response when fetching nonce"""
    response_data = {"error": "Service unavailable"}
    mock_client = MockAsyncClient(
        "https://egauge12345.local/api/auth/unauthorized",
        response_data,
        status_code=503,
    )

    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )

    with pytest.raises(EgaugeAuthenticationError):
        await handler._fetch_nonce()


# Test _perform_login()
@pytest.mark.asyncio
async def test_perform_login_success():
    """Test successful login with digest authentication"""
    nonce_response = NonceResponse(
        realm="eGauge Administration",
        nonce="server_nonce_123",
        error="Authentication required.",
    )

    response_data = {
        "jwt": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcdef"
    }
    mock_client = MockAsyncClient(
        "https://egauge12345.local/api/auth/login", response_data
    )

    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "testpass", mock_client
    )
    auth_response = await handler._perform_login(nonce_response)

    assert (
        auth_response.jwt
        == "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcdef"
    )
    assert len(mock_client.calls) == 1
    assert mock_client.calls[0][0] == "POST"

    # Verify request body structure
    request_body = mock_client.calls[0][2]
    assert request_body["rlm"] == "eGauge Administration"
    assert request_body["usr"] == "owner"
    assert request_body["nnc"] == "server_nonce_123"
    assert "cnnc" in request_body
    assert len(request_body["cnnc"]) == 32  # Client nonce should be 32-char hex
    assert "hash" in request_body


@pytest.mark.asyncio
async def test_perform_login_invalid_credentials():
    """Test login failure with invalid credentials (eGauge returns 200 with error field)"""
    nonce_response = NonceResponse(
        realm="eGauge Administration",
        nonce="server_nonce_123",
        error="Authentication required.",
    )

    # eGauge returns 200 status with error field for bad credentials
    response_data = {"error": "Invalid credentials"}
    mock_client = MockAsyncClient(
        "https://egauge12345.local/api/auth/login", response_data, status_code=200
    )

    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "wrongpass", mock_client
    )

    with pytest.raises(
        EgaugeAuthenticationError, match="Login failed: Invalid credentials"
    ):
        await handler._perform_login(nonce_response)


@pytest.mark.asyncio
async def test_perform_login_malformed_response():
    """Test login with malformed response (no jwt and no error field)"""
    from egauge_async.exceptions import EgaugeParsingException

    nonce_response = NonceResponse(
        realm="eGauge Administration",
        nonce="server_nonce_123",
        error="Authentication required.",
    )

    # Malformed response: missing both jwt and error fields
    response_data = {"some_other_field": "unexpected"}
    mock_client = MockAsyncClient(
        "https://egauge12345.local/api/auth/login", response_data, status_code=200
    )

    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )

    with pytest.raises(
        EgaugeParsingException,
        match="Login response missing both 'jwt' and 'error' fields",
    ):
        await handler._perform_login(nonce_response)


# Test get_token()
@pytest.mark.asyncio
async def test_get_token_lazy_authentication():
    """Test that get_token() authenticates on first call"""
    test_jwt = create_egauge_jwt()

    mock_client = MultiResponseClient()
    mock_client.add_get_handler(
        "/api/auth/unauthorized",
        {
            "rlm": "eGauge Administration",
            "nnc": "server_nonce_123",
            "error": "Authentication required.",
        },
        status_code=401,
    )
    mock_client.add_post_handler("/api/auth/login", {"jwt": test_jwt})

    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )

    # First call should authenticate
    token = await handler.get_token()

    assert token == test_jwt
    assert handler._token_state is not None
    assert handler._token_state.token == test_jwt
    # Should have made 2 calls: get nonce, then login
    assert len(mock_client.calls) == 2
    assert mock_client.calls[0][0] == "GET"
    assert mock_client.calls[1][0] == "POST"


@pytest.mark.asyncio
async def test_get_token_caching():
    """Test that get_token() returns cached token on subsequent calls"""
    test_jwt = create_egauge_jwt()

    mock_client = MultiResponseClient()
    mock_client.add_get_handler(
        "/api/auth/unauthorized",
        {
            "rlm": "eGauge Administration",
            "nnc": "server_nonce_123",
            "error": "Authentication required.",
        },
        status_code=401,
    )
    mock_client.add_post_handler("/api/auth/login", {"jwt": test_jwt})

    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )

    # First call
    token1 = await handler.get_token()
    call_count_after_first = len(mock_client.calls)

    # Second call should use cached token
    token2 = await handler.get_token()

    assert token1 == token2
    assert len(mock_client.calls) == call_count_after_first  # No new calls
    assert token2 == test_jwt


@pytest.mark.asyncio
async def test_get_token_already_authenticated():
    """Test get_token() when token is already set"""

    mock_client = NeverCalledClient()
    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )

    # Manually set token state with far-future expiration
    handler._token_state = _TokenState(
        token="existing_token",
        expiry_timestamp=time.time() + 3600,  # Expires in 1 hour
        issued_at=time.time(),
    )

    token = await handler.get_token()

    assert token == "existing_token"


# Test logout()
@pytest.mark.asyncio
async def test_logout_success():
    """Test successful logout"""

    response_data = {"status": "Token revoked successfully"}
    mock_client = MockAsyncClient(
        "https://egauge12345.local/api/auth/logout", response_data
    )

    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )
    # Set token state
    handler._token_state = _TokenState(
        token="test_token_to_revoke",
        expiry_timestamp=time.time() + 600,
        issued_at=time.time(),
    )

    await handler.logout()

    # Token state should be cleared
    assert handler._token_state is None
    # Should have made a GET request to /api/auth/logout
    assert len(mock_client.calls) == 1
    assert mock_client.calls[0][0] == "GET"


@pytest.mark.asyncio
async def test_logout_when_not_authenticated():
    """Test logout when no token is set (should call server but not error)"""
    response_data = {"status": "OK"}
    mock_client = MockAsyncClient(
        "https://egauge12345.local/api/auth/logout", response_data
    )
    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )

    # No token set
    assert handler._token_state is None

    # Should not raise any errors (calls server even without token)
    await handler.logout()

    # Still no token
    assert handler._token_state is None
