import asyncio
import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass

import httpx

from egauge_async.exceptions import EgaugeAuthenticationError, EgaugeParsingException
from egauge_async.json.models import NonceResponse, AuthResponse


@dataclass
class _TokenState:
    """Internal state for JWT token management."""

    token: str
    expiry_timestamp: float
    issued_at: float


# Constants for token management
MIN_REFRESH_BUFFER_SECONDS = 1  # Minimum seconds before expiry to refresh
MAX_REFRESH_BUFFER_SECONDS = (
    600  # Maximum seconds before expiry to refresh (10 minutes)
)
MAX_TOKEN_LIFETIME_SECONDS = 86400  # Maximum expected token lifetime (24 hours)


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
        if (
            not MIN_REFRESH_BUFFER_SECONDS
            <= refresh_buffer_seconds
            < MAX_REFRESH_BUFFER_SECONDS
        ):
            raise ValueError(
                f"refresh_buffer_seconds must be between {MIN_REFRESH_BUFFER_SECONDS} "
                f"and {MAX_REFRESH_BUFFER_SECONDS}, got {refresh_buffer_seconds}"
            )

    @staticmethod
    def _parse_jwt_expiry(token: str) -> float:
        """Extract expiration timestamp from JWT payload.

        Args:
            token: JWT token string (header.payload.signature format)

        Returns:
            Unix timestamp of expiration (calculated as beg + ltm)

        Raises:
            EgaugeParsingException: If JWT is malformed or missing required fields

        Notes:
            eGauge JWTs use 'beg' (begin timestamp) and 'ltm' (lifetime in seconds)
            instead of the standard 'exp' field. Expiration is calculated as beg + ltm.
            Does not validate signature, only extracts claims.
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

            # eGauge uses 'beg' (begin) and 'ltm' (lifetime) instead of 'exp'
            beg = payload_json.get("beg")
            ltm = payload_json.get("ltm")

            if beg is None:
                raise EgaugeParsingException(
                    "JWT missing 'beg' (begin timestamp) claim"
                )

            if ltm is None:
                raise EgaugeParsingException("JWT missing 'ltm' (lifetime) claim")

            # Convert string to number if needed
            if isinstance(beg, str):
                try:
                    beg = float(beg)
                except ValueError:
                    raise EgaugeParsingException(
                        f"JWT 'beg' claim must be numeric, got invalid string: '{beg}'"
                    )
            if isinstance(ltm, str):
                try:
                    ltm = float(ltm)
                except ValueError:
                    raise EgaugeParsingException(
                        f"JWT 'ltm' claim must be numeric, got invalid string: '{ltm}'"
                    )

            if not isinstance(beg, (int, float)):
                raise EgaugeParsingException(
                    f"JWT 'beg' claim must be numeric, got {type(beg).__name__}"
                )

            if not isinstance(ltm, (int, float)):
                raise EgaugeParsingException(
                    f"JWT 'ltm' claim must be numeric, got {type(ltm).__name__}"
                )

            # Validate lifetime is reasonable (positive and not excessive)
            if ltm <= 0:
                raise EgaugeParsingException(
                    f"JWT 'ltm' (lifetime) must be positive, got {ltm}"
                )
            if ltm > MAX_TOKEN_LIFETIME_SECONDS:
                raise EgaugeParsingException(
                    f"JWT 'ltm' (lifetime) is too long (more than {MAX_TOKEN_LIFETIME_SECONDS} seconds): {ltm}"
                )

            # Calculate expiration timestamp
            expiry = beg + ltm

            # Validate the calculated expiry is in the future
            now = time.time()
            if expiry < now:
                raise EgaugeParsingException(
                    f"JWT already expired (beg={beg}, ltm={ltm}, expiry={expiry}, now={now})"
                )

            return float(expiry)

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
        """Fetch server nonce from /api/auth/unauthorized endpoint

        Returns:
            NonceResponse containing realm and server nonce

        Raises:
            EgaugeAuthenticationError: If the request fails

        Notes:
            The /api/auth/unauthorized endpoint returns 401 status code by design,
            providing nonce data in the response body for digest authentication.
        """
        url = f"{self.base_url}/api/auth/unauthorized"
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

        url = f"{self.base_url}/api/auth/login"
        response = await self.client.post(
            url,
            json={
                "rlm": nonce_response.realm,
                "usr": self.username,
                "nnc": nonce_response.nonce,
                "cnnc": client_nonce,
                "hash": digest_hash,
            },
        )

        if response.status_code != 200:
            raise EgaugeAuthenticationError(
                f"Login failed: HTTP {response.status_code}"
            )

        data = response.json()

        # Check for error in response (eGauge returns 200 with error field for bad credentials)
        if "error" in data:
            raise EgaugeAuthenticationError(f"Login failed: {data['error']}")

        # Verify JWT is present (if no error and no jwt, response is malformed)
        if "jwt" not in data:
            raise EgaugeParsingException(
                "Login response missing both 'jwt' and 'error' fields"
            )

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
        1. Checks if a token exists
        2. If token exists: invalidates local cache and notifies server
        3. If no token: this is a no-op

        Raises:
            EgaugeAuthenticationError: If the logout request fails
        """
        # Check if we have a token to revoke
        async with self._token_lock:
            if self._token_state is None:
                return  # No-op if not authenticated

            # Save token for server notification before clearing
            token = self._token_state.token
            # Invalidate local cache first (prevents use even if server call fails)
            self._token_state = None

        # Notify server to revoke the token
        url = f"{self.base_url}/api/auth/logout"
        headers = {"Authorization": f"Bearer {token}"}
        response = await self.client.get(url, headers=headers)

        if response.status_code != 200:
            raise EgaugeAuthenticationError(
                f"Logout failed: HTTP {response.status_code}"
            )
