"""Configuration loading.

Reads from environment variables. See .env.example for the expected shape.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    keycloak_url: str
    realm: str
    client_id: str
    client_secret: str
    inactivity_days: int
    dry_run: bool
    exclusions: list[str]

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()

        client_secret = os.environ.get("KEYCLOAK_CLIENT_SECRET")
        if not client_secret:
            raise ValueError("KEYCLOAK_CLIENT_SECRET is required")

        exclusions = [
            name.strip()
            for name in os.environ.get("EXCLUSIONS", "").split(",")
            if name.strip()
        ]

        return cls(
            keycloak_url=os.environ.get("KEYCLOAK_URL", "http://localhost:8080"),
            realm=os.environ.get("KEYCLOAK_REALM", "acme"),
            client_id=os.environ.get("KEYCLOAK_CLIENT_ID", "user-cleanup-service"),
            client_secret=client_secret,
            inactivity_days=int(os.environ.get("INACTIVITY_DAYS", "120")),
            dry_run=os.environ.get("DRY_RUN", "true").strip().lower() == "true",
            exclusions=exclusions,
        )
