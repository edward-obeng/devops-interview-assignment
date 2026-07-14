"""Entry point.

Run with:
    python -m cleaner.main

Flow:
    1. Load config from environment
    2. Build a Keycloak client
    3. List users, filter for stale ones (respect exclusions)
    4. If dry-run, log the candidates. Otherwise, disable them.
    5. Emit a summary log line
"""

import logging
import sys
import time

from .config import Config
from .keycloak_client import KeycloakClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("cleaner")

SECONDS_PER_DAY = 86400


def _last_login_days_ago(user: dict, now: float) -> float | None:
    """Age in days since the seeded `lastLogin` attribute (epoch ms). None if absent."""
    values = (user.get("attributes") or {}).get("lastLogin")
    if not values:
        return None
    return (now - int(values[0]) / 1000) / SECONDS_PER_DAY


def main() -> int:
    config = Config.from_env()
    client = KeycloakClient(
        base_url=config.keycloak_url,
        realm=config.realm,
        client_id=config.client_id,
        client_secret=config.client_secret,
    )

    now = time.time()
    users = client.list_users()

    disabled = excluded = no_signal = kept_active = 0

    for user in users:
        username = user["username"]

        if username in config.exclusions:
            excluded += 1
            logger.info("action=skip reason=excluded username=%s", username)
            continue

        age_days = _last_login_days_ago(user, now)
        if age_days is None:
            no_signal += 1
            logger.warning("action=skip reason=no_last_login_signal username=%s", username)
            continue

        if age_days < config.inactivity_days:
            kept_active += 1
            continue

        if config.dry_run:
            logger.info(
                "action=would_disable username=%s user_id=%s age_days=%.1f dry_run=true",
                username, user["id"], age_days,
            )
        else:
            client.disable_user(user["id"])
            logger.info(
                "action=disable username=%s user_id=%s age_days=%.1f dry_run=false",
                username, user["id"], age_days,
            )
        disabled += 1

    logger.info(
        "summary realm=%s total_users=%d disabled=%d excluded=%d kept_active=%d no_signal=%d dry_run=%s",
        config.realm, len(users), disabled, excluded, kept_active, no_signal, config.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
