from dataclasses import dataclass
from enum import StrEnum


class RegisterType(StrEnum):
    VOLTAGE = "V"
    POWER = "P"
    CURRENT = "I"


@dataclass
class NonceResponse:
    """Response from /auth/unauthorized endpoint containing server nonce"""

    realm: str
    nonce: str
    error: str | None = None


@dataclass
class LoginRequest:
    """Request body for /auth/login endpoint using digest authentication"""

    rlm: str
    usr: str
    nnc: str
    cnnc: str
    hash: str


@dataclass
class AuthResponse:
    """Response from /auth/login endpoint containing JWT token"""

    jwt: str
    error: str | None = None
