import asyncio
import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass

import httpx

from egauge_async.exceptions import EgaugeAuthenticationError, EgaugeParsingException
from egauge_async.json.models import NonceResponse, LoginRequest, AuthResponse


@dataclass
class _TokenState:
    """Internal state for JWT token management."""

    token: str
    expiry_timestamp: float
    issued_at: float


class JwtAuthManager:
    """Handles JWT token authentication for the eGauge JSON API with automatic refresh"""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        client: httpx.AsyncClient,
        refresh_buffer_seconds: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.client = client
        self._token_state: _TokenState | None = None
        self._token_lock: asyncio.Lock = asyncio.Lock()
        self._refresh_buffer_seconds = refresh_buffer_seconds

        # Validate buffer
        if not 0 < refresh_buffer_seconds < 600:
            raise ValueError(
                f"refresh_buffer_seconds must be between 0 and 600, got {refresh_buffer_seconds}"
            )

    @staticmethod
    def _parse_jwt_expiry(token: str) -> float:
        """Extract expiration timestamp from JWT payload.

        Args:
            token: JWT token string (header.payload.signature format)

        Returns:
            Unix timestamp of expiration

        Raises:
            EgaugeParsingException: If JWT is malformed or missing exp claim

        Notes:
            Does not validate signature, only extracts exp claim.
            Uses base64 decoding without external dependencies.
        """
        try:
            # JWT structure: header.payload.signature
            parts = token.split(".")
            if len(parts) < 2:
                raise EgaugeParsingException(
                    "Malformed JWT: token must have at least 2 segments (header.payload)"
                )

            # Decode payload (add padding if needed)
            payload_encoded = parts[1]
            padding_needed = 4 - (len(payload_encoded) % 4)
            if padding_needed != 4:
                payload_encoded += "=" * padding_needed

            payload_decoded = base64.urlsafe_b64decode(payload_encoded)
            payload_json = json.loads(payload_decoded)

            exp = payload_json.get("exp")
            if exp is None:
                raise EgaugeParsingException("JWT missing 'exp' (expiration) claim")

            # Convert string to number if needed
            if isinstance(exp, str):
                exp = float(exp)

            if not isinstance(exp, (int, float)):
                raise EgaugeParsingException(
                    f"JWT 'exp' claim must be numeric, got {type(exp).__name__}"
                )

            # Validate range (must be reasonable timestamp)
            now = time.time()
            if exp < now:
                raise EgaugeParsingException(
                    "JWT 'exp' claim is in the past (token already expired)"
                )
            if exp > now + 86400:  # Not within next 24 hours
                raise EgaugeParsingException(
                    "JWT 'exp' claim is too far in the future (more than 24 hours)"
                )

            return float(exp)

        except (ValueError, json.JSONDecodeError) as e:
            raise EgaugeParsingException(f"Failed to decode JWT payload: {e}")

    @staticmethod
    def _generate_client_nonce() -> str:
        """Generate a cryptographically secure client nonce

        Returns:
            A 32-character hexadecimal string
        """
        return secrets.token_hex(16)

    @staticmethod
    def _calculate_digest_hash(
        username: str,
        password: str,
        realm: str,
        server_nonce: str,
        client_nonce: str,
    ) -> str:
        """Calculate the digest authentication hash

        Args:
            username: Username for authentication
            password: Password for authentication
            realm: Authentication realm from server
            server_nonce: Server-provided nonce
            client_nonce: Client-generated nonce

        Returns:
            MD5 hash string for digest authentication
        """
        ha1 = hashlib.md5(f"{username}:{realm}:{password}".encode()).hexdigest()
        return hashlib.md5(f"{ha1}:{server_nonce}:{client_nonce}".encode()).hexdigest()

    async def _fetch_nonce(self) -> NonceResponse:
        """Fetch server nonce from /auth/unauthorized endpoint

        Returns:
            NonceResponse containing realm and server nonce

        Raises:
            EgaugeAuthenticationError: If the request fails

        Notes:
            The /auth/unauthorized endpoint returns 401 status code by design,
            providing nonce data in the response body for digest authentication.
        """
        url = f"{self.base_url}/auth/unauthorized"
        response = await self.client.get(url)

        if response.status_code != 401:
            raise EgaugeAuthenticationError(
                f"Failed to fetch nonce: HTTP {response.status_code}"
            )

        data = response.json()
        return NonceResponse(
            realm=data["rlm"], nonce=data["nnc"], error=data.get("error")
        )

    def _is_token_valid(self) -> bool:
        """Check if cached token is still valid (not expired with buffer).

        Returns:
            True if token exists and is not expired (considering buffer)
        """
        if self._token_state is None:
            return False

        now = time.time()
        expiry_with_buffer = (
            self._token_state.expiry_timestamp - self._refresh_buffer_seconds
        )
        return now < expiry_with_buffer

    async def _perform_login(self, nonce_response: NonceResponse) -> AuthResponse:
        """Perform login using digest authentication

        Args:
            nonce_response: Server nonce response from _fetch_nonce()

        Returns:
            AuthResponse containing JWT token

        Raises:
            EgaugeAuthenticationError: If login fails
        """
        client_nonce = self._generate_client_nonce()
        digest_hash = self._calculate_digest_hash(
            self.username,
            self.password,
            nonce_response.realm,
            nonce_response.nonce,
            client_nonce,
        )

        login_request = LoginRequest(
            rlm=nonce_response.realm,
            usr=self.username,
            nnc=nonce_response.nonce,
            cnnc=client_nonce,
            hash=digest_hash,
        )

        url = f"{self.base_url}/auth/login"
        response = await self.client.post(
            url,
            json={
                "rlm": login_request.rlm,
                "usr": login_request.usr,
                "nnc": login_request.nnc,
                "cnnc": login_request.cnnc,
                "hash": login_request.hash,
            },
        )

        if response.status_code != 200:
            print(response.text)
            raise EgaugeAuthenticationError(
                f"Login failed: HTTP {response.status_code}"
            )

        data = response.json()
        return AuthResponse(jwt=data["jwt"], error=data.get("error"))

    async def get_token(self) -> str:
        """Get a valid JWT token, refreshing if necessary.

        This method is thread-safe and handles concurrent calls efficiently.
        Tokens are refreshed proactively before expiration to prevent failed requests.

        Uses double-checked locking: first check without lock (fast path),
        then recheck with lock if refresh needed (slow path).

        Returns:
            A valid JWT token string (guaranteed not expired for at least
            refresh_buffer_seconds)

        Raises:
            EgaugeAuthenticationError: If authentication fails
        """
        # Fast path: check validity without lock
        if self._is_token_valid():
            return self._token_state.token  # type: ignore

        # Slow path: acquire lock and recheck
        async with self._token_lock:
            # Recheck after acquiring lock (another coroutine may have refreshed)
            if self._is_token_valid():
                return self._token_state.token  # type: ignore

            # Actually need to refresh/authenticate
            return await self._authenticate_and_cache()

    async def _authenticate_and_cache(self) -> str:
        """Perform authentication and cache the new token with expiry.

        Must be called while holding _token_lock.

        Returns:
            New JWT token string

        Raises:
            EgaugeAuthenticationError: If authentication fails (bad credentials, network error)
            EgaugeParsingException: If JWT token from server is malformed
        """
        # Perform two-step authentication
        nonce_response = await self._fetch_nonce()
        auth_response = await self._perform_login(nonce_response)
        token = auth_response.jwt

        # Parse expiration from token (raises exception if invalid)
        expiry_timestamp = self._parse_jwt_expiry(token)

        # Cache token with expiry
        self._token_state = _TokenState(
            token=token, expiry_timestamp=expiry_timestamp, issued_at=time.time()
        )

        return token

    async def invalidate_token(self) -> None:
        """Immediately invalidate the cached token.

        Used when a 401 response indicates the token is no longer valid.
        The next call to get_token() will trigger re-authentication.

        This is different from logout() which also notifies the server.
        This is thread-safe and can be called concurrently with get_token().
        """
        async with self._token_lock:
            self._token_state = None

    async def logout(self) -> None:
        """Revoke the current JWT token and clear the cache.

        This method:
        1. Invalidates the local cache immediately
        2. Notifies the server to revoke the token

        If no token is currently set, this is a no-op.

        Raises:
            EgaugeAuthenticationError: If the logout request fails
        """
        # Invalidate local cache first (prevents use even if server call fails)
        await self.invalidate_token()

        # Notify server
        url = f"{self.base_url}/auth/logout"
        response = await self.client.get(url)

        if response.status_code != 200:
            raise EgaugeAuthenticationError(
                f"Logout failed: HTTP {response.status_code}"
            )
