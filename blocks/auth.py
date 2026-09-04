"""
blocks/auth.py

Session-cookie login gate for the deployed API - a single shared passphrase
(SIFTPIPE_ADMIN_PASSWORD), not per-user accounts, since there's only one
audience tier for this demo box. See docs/next-steps-before-deployment.md's
Security section for the full design rationale (why no database, the two
secrets this needs, the cross-domain cookie/rate-limiter fixes).
"""

import hashlib
import hmac
import os
import time

from blocks.pipeline import MissingConfigError

REQUIRED_ENV_VARS = ("SIFTPIPE_ADMIN_PASSWORD", "SIFTPIPE_SESSION_SECRET")


def validate_required_env_vars():
    """Fail fast at API startup if the login gate's secrets aren't set -
    mirrors blocks/pipeline.py's validate_required_env_vars() for
    ANTHROPIC_API_KEY: a missing secret should surface at boot, not as a
    confusing failure on the first login attempt."""
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise MissingConfigError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in .env before running the API."
        )


def verify_password(submitted: str) -> bool:
    """Constant-time comparison against SIFTPIPE_ADMIN_PASSWORD. Plain `==`
    on strings short-circuits at the first mismatched character, so how long
    a wrong guess takes to reject leaks how many leading characters it got
    right. hmac.compare_digest fixes that for equal-length inputs, but a
    wrong-length guess can still short-circuit and leak that the length
    itself was wrong - hashing both sides to a fixed-length digest first
    closes that too, so timing reveals nothing about the guess at all."""
    expected = os.getenv("SIFTPIPE_ADMIN_PASSWORD", "")
    submitted_hash = hashlib.sha256(submitted.encode("utf-8")).digest()
    expected_hash = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(submitted_hash, expected_hash)


# In-memory login rate limiter, keyed by client IP. Resets on every process
# restart and isn't shared across worker processes - a speed bump against
# casual guessing on a single-box demo deployment, not real brute-force
# protection (would need Redis or similar for that). _client_ip() in api.py
# reads a trusted X-Forwarded-For once nginx is actually in front of this
# (FRONTEND_ORIGIN set), matching the doc's AWS-compatibility finding that
# request.client.host alone would collapse every visitor into one shared
# bucket behind a reverse proxy.
_attempts: dict[str, list[float]] = {}
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60


def check_rate_limit(client_ip: str) -> bool:
    """True if this IP may attempt a login right now. Also prunes attempts
    older than WINDOW_SECONDS, so a window's failures don't count forever."""
    now = time.time()
    recent = [t for t in _attempts.get(client_ip, []) if now - t < WINDOW_SECONDS]
    _attempts[client_ip] = recent
    return len(recent) < MAX_ATTEMPTS


def record_failed_attempt(client_ip: str) -> None:
    _attempts.setdefault(client_ip, []).append(time.time())


def reset_attempts(client_ip: str) -> None:
    """Clear on a successful login so a legitimate user who mistyped once
    isn't stuck waiting out the window after they get it right."""
    _attempts.pop(client_ip, None)
