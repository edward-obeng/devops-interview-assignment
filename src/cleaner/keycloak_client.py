"""Keycloak Admin API client.

Fetches a client_credentials token, lists users in a realm, and disables
(soft-deletes) a user. Uses httpx directly rather than a wrapper library —
see DECISIONS.md for why.
"""

import httpx

PAGE_SIZE = 100


class KeycloakClient:
    def __init__(self, base_url: str, realm: str, client_id: str, client_secret: str):
        self.base_url = base_url.rstrip("/")
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None

    def get_token(self) -> str:
        response = httpx.post(
            f"{self.base_url}/realms/{self.realm}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def _auth_headers(self) -> dict[str, str]:
        if self._token is None:
            self._token = self.get_token()
        return {"Authorization": f"Bearer {self._token}"}

    def list_users(self) -> list[dict]:
        users = []
        first = 0
        while True:
            response = httpx.get(
                f"{self.base_url}/admin/realms/{self.realm}/users",
                headers=self._auth_headers(),
                params={"first": first, "max": PAGE_SIZE},
            )
            response.raise_for_status()
            page = response.json()
            users.extend(page)
            if len(page) < PAGE_SIZE:
                break
            first += PAGE_SIZE
        return users

    def disable_user(self, user_id: str) -> None:
        response = httpx.put(
            f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}",
            headers=self._auth_headers(),
            json={"enabled": False},
        )
        response.raise_for_status()
