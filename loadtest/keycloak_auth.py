"""
Keycloak token generation and handling for simulated Locust student users.

Each simulated user gets its own KeycloakTokenManager, which logs in once via
the Resource Owner Password Credentials grant and transparently refreshes (or
re-logs in) as the token nears expiry. Token requests go straight to Keycloak
via the `keycloak` client library, not through Locust's HttpUser session, so
they don't pollute the backend's request stats.
"""

import sys
import time
from itertools import count
from pathlib import Path
from threading import Lock

# Add project root to sys.path so `app.core.config` is importable regardless
# of the working directory Locust is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import config
from keycloak import KeycloakOpenID

DEFAULT_PASSWORD = "1234"
USERNAME_PREFIX = "student"

# How far ahead of expiry (in seconds) to proactively refresh/re-login.
EXPIRY_LEEWAY_SECONDS = 10

# The reverse proxy in front of Keycloak resets connections that don't send a
# browser-like User-Agent (e.g. the default `python-requests/x.x` UA), so we
# spoof one on every request this client makes.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class KeycloakTokenManager:
    """Logs a single student user in and keeps their access token fresh."""

    def __init__(self, username: str, password: str = DEFAULT_PASSWORD):
        self.username = username
        self.password = password
        self._client = KeycloakOpenID(
            server_url=config.KEYCLOAK_SERVER_URL,
            realm_name=config.KEYCLOAK_REALM,
            client_id=config.KEYCLOAK_CLIENT_ID,
            client_secret_key=config.KEYCLOAK_CLIENT_SECRET,
            verify=config.ENVIRONMENT == "production",
            custom_headers={"User-Agent": BROWSER_USER_AGENT},
        )
        self._token: dict | None = None
        self._expires_at: float = 0
        self._refresh_expires_at: float = 0

    def login(self) -> str:
        """Perform the ROPC grant and cache the resulting token."""
        self._token = self._client.token(username=self.username, password=self.password)
        self._set_expiry()
        return self._token["access_token"]

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing or re-logging in as needed."""
        now = time.time()

        if self._token and now < self._expires_at - EXPIRY_LEEWAY_SECONDS:
            return self._token["access_token"]

        if self._token and now < self._refresh_expires_at - EXPIRY_LEEWAY_SECONDS:
            try:
                self._token = self._client.refresh_token(self._token["refresh_token"])
                self._set_expiry()
                return self._token["access_token"]
            except Exception:
                pass  # refresh token turned out to be invalid - fall back to login

        return self.login()

    def _set_expiry(self):
        now = time.time()
        self._expires_at = now + self._token.get("expires_in", 60)
        self._refresh_expires_at = now + self._token.get("refresh_expires_in", 1800)


class StudentUsernamePool:
    """Hands out student1, student2, ... usernames, wrapping around a pool size."""

    def __init__(self, pool_size: int):
        self.pool_size = pool_size
        self._counter = count()
        self._lock = Lock()

    def acquire(self) -> str:
        with self._lock:
            n = next(self._counter)
        index = (n % self.pool_size) + 1
        return f"{USERNAME_PREFIX}{index}"
