import hashlib

import pytest

from egauge_async.exceptions import EgaugeAuthenticationError
from egauge_async.json.auth import JwtAuthManager
from egauge_async.json.models import NonceResponse
from mocks import MockAsyncClient, MultiResponseClient, NeverCalledClient


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


# Test _fetch_nonce()
@pytest.mark.asyncio
async def test_fetch_nonce_success():
    """Test successfully fetching server nonce from /auth/unauthorized"""
    response_data = {
        "rlm": "eGauge Administration",
        "nnc": "eyJ0eXAiJkpXVCJ9.eyJzdWIi.w5GCvM",
        "error": "Authentication required.",
    }
    mock_client = MockAsyncClient(
        "https://egauge12345.local/auth/unauthorized", response_data
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
        "https://egauge12345.local/auth/unauthorized", response_data, status_code=503
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
    mock_client = MockAsyncClient("https://egauge12345.local/auth/login", response_data)

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
    """Test login failure with invalid credentials"""
    nonce_response = NonceResponse(
        realm="eGauge Administration",
        nonce="server_nonce_123",
        error="Authentication required.",
    )

    response_data = {"error": "Invalid credentials"}
    mock_client = MockAsyncClient(
        "https://egauge12345.local/auth/login", response_data, status_code=400
    )

    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "wrongpass", mock_client
    )

    with pytest.raises(EgaugeAuthenticationError):
        await handler._perform_login(nonce_response)


# Test get_token()
@pytest.mark.asyncio
async def test_get_token_lazy_authentication():
    """Test that get_token() authenticates on first call"""
    mock_client = MultiResponseClient()
    mock_client.add_get_handler(
        "/auth/unauthorized",
        {
            "rlm": "eGauge Administration",
            "nnc": "server_nonce_123",
            "error": "Authentication required.",
        },
    )
    mock_client.add_post_handler("/auth/login", {"jwt": "test_jwt_token_abc123"})

    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )

    # First call should authenticate
    token = await handler.get_token()

    assert token == "test_jwt_token_abc123"
    assert handler._jwt_token == "test_jwt_token_abc123"
    # Should have made 2 calls: get nonce, then login
    assert len(mock_client.calls) == 2
    assert mock_client.calls[0][0] == "GET"
    assert mock_client.calls[1][0] == "POST"


@pytest.mark.asyncio
async def test_get_token_caching():
    """Test that get_token() returns cached token on subsequent calls"""
    mock_client = MultiResponseClient()
    mock_client.add_get_handler(
        "/auth/unauthorized",
        {
            "rlm": "eGauge Administration",
            "nnc": "server_nonce_123",
            "error": "Authentication required.",
        },
    )
    mock_client.add_post_handler("/auth/login", {"jwt": "test_jwt_token_abc123"})

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
    assert token2 == "test_jwt_token_abc123"


@pytest.mark.asyncio
async def test_get_token_already_authenticated():
    """Test get_token() when token is already set"""
    mock_client = NeverCalledClient()
    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )

    # Manually set token
    handler._jwt_token = "existing_token"

    token = await handler.get_token()

    assert token == "existing_token"


# Test logout()
@pytest.mark.asyncio
async def test_logout_success():
    """Test successful logout"""
    response_data = {"status": "Token revoked successfully"}
    mock_client = MockAsyncClient(
        "https://egauge12345.local/auth/logout", response_data
    )

    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )
    handler._jwt_token = "test_token_to_revoke"

    await handler.logout()

    # Token should be cleared
    assert handler._jwt_token is None
    # Should have made a GET request to /auth/logout
    assert len(mock_client.calls) == 1
    assert mock_client.calls[0][0] == "GET"


@pytest.mark.asyncio
async def test_logout_when_not_authenticated():
    """Test logout when no token is set (should be a no-op)"""
    mock_client = NeverCalledClient()
    handler = JwtAuthManager(
        "https://egauge12345.local", "owner", "password", mock_client
    )

    # No token set
    assert handler._jwt_token is None

    # Should not raise any errors
    await handler.logout()

    # Still no token
    assert handler._jwt_token is None
