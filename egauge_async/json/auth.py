import hashlib
import secrets

import httpx

from egauge_async.exceptions import EgaugeAuthenticationError
from egauge_async.json.models import NonceResponse, LoginRequest, AuthResponse


class JwtAuthManager:
    """Handles JWT token authentication for the eGauge JSON API"""

    def __init__(
        self, base_url: str, username: str, password: str, client: httpx.AsyncClient
    ):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.client = client
        self._jwt_token: str | None = None

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
        """
        url = f"{self.base_url}/auth/unauthorized"
        response = await self.client.get(url)

        if response.status_code != 200:
            raise EgaugeAuthenticationError(
                f"Failed to fetch nonce: HTTP {response.status_code}"
            )

        data = response.json()
        return NonceResponse(
            realm=data["rlm"], nonce=data["nnc"], error=data.get("error")
        )

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
            raise EgaugeAuthenticationError(
                f"Login failed: HTTP {response.status_code}"
            )

        data = response.json()
        return AuthResponse(jwt=data["jwt"], error=data.get("error"))

    async def get_token(self) -> str:
        """Get a valid JWT token, authenticating if necessary

        This method implements lazy authentication. On the first call, it will
        fetch a nonce and perform login. On subsequent calls, it returns the
        cached token.

        Returns:
            A valid JWT token string

        Raises:
            EgaugeAuthenticationError: If authentication fails
        """
        if self._jwt_token is not None:
            return self._jwt_token

        # Perform authentication
        nonce_response = await self._fetch_nonce()
        auth_response = await self._perform_login(nonce_response)
        self._jwt_token = auth_response.jwt

        return self._jwt_token

    async def logout(self) -> None:
        """Revoke the current JWT token and clear the cache

        If no token is currently set, this is a no-op.

        Raises:
            EgaugeAuthenticationError: If the logout request fails
        """
        if self._jwt_token is None:
            return

        url = f"{self.base_url}/auth/logout"
        response = await self.client.get(url)

        # Clear the token regardless of response status
        self._jwt_token = None

        if response.status_code != 200:
            raise EgaugeAuthenticationError(
                f"Logout failed: HTTP {response.status_code}"
            )
