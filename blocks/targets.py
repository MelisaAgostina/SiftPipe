"""
blocks/targets.py — Target-profile abstraction (MULTI_TARGET_PLAN.md Phase 1).

A TargetProfile describes everything the pipeline needs to point itself at a
different site without touching B1/B4/B7's own logic: where it lives, how to
log in, which env vars hold credentials, and how to tell a successful login
apart from a failed one. Mattermost's profile reuses the exact selector lists
already used by blocks/mattermost_auth.py (single source of truth, zero
behavior change) instead of duplicating them.

This module only defines the shape and the two concrete profiles. Wiring B4's
discovery and B7's login/injection flow to actually *use* a profile instead
of their current Mattermost-only constants is Phase 2/3 — selecting a target
here (Task 1.2) just loads the right data, it doesn't change block behavior
yet.
"""

from dataclasses import dataclass
import os

from dotenv import load_dotenv

from blocks.mattermost_auth import LOGIN_ID_SELECTORS as _MM_LOGIN_ID_SELECTORS
from blocks.mattermost_auth import PASSWORD_SELECTORS as _MM_PASSWORD_SELECTORS

# Called here, not just relied on from a caller (main.py/api.py both already
# call it before importing this module) — credential resolution
# (TargetProfile.username/.password below) needs .env loaded regardless of
# who imports this module first. Found live during Phase 3 verification: a
# throwaway script importing blocks.targets directly, without main.py's
# import chain, silently got each password property's "" fallback default
# instead of the real .env value. python-dotenv's load_dotenv() is
# idempotent and mutates os.environ globally, so calling it again from
# main.py/api.py afterwards is a harmless no-op.
load_dotenv()


@dataclass(frozen=True)
class TargetProfile:
    """
    One instance per real target. Selector lists are ordered
    most-specific/current first, same convention find_working_selector()
    already uses for Mattermost.
    """
    name: str
    display_name: str        # human-readable, for the frontend's target picker (Phase 5)
    stack_label: str         # short "what's running" subtitle shown next to display_name
    base_url_env: str
    base_url_default: str
    login_path: str
    login_id_selectors: list
    password_selectors: list
    submit_selectors: list        # tried in order; last resort is "Enter" on the password field
    username_env: str
    username_default: str
    password_env: str
    password_default: str
    authenticated_selectors: list  # any one present on the page = login succeeded
    supports_fresh_reset: bool     # can B1 wipe+reseed this target's data store?
    extra_denylist: list           # path substrings B4's crawler (blocks/crawler.py) skips, on top of the generic set
    source_dir: str                # local checkout B3 (blocks/static_scanner.py) scans
    source_extensions: tuple       # file extensions to include - target's real tech stack, not a generic guess
    source_exclude_dirs: frozenset  # directory names never walked at all (deps, migrations, vcs)
    source_relevant_dirs: frozenset  # None = no directory-name filter; otherwise only files under one of these dir names are included

    @property
    def base_url(self) -> str:
        return os.getenv(self.base_url_env, self.base_url_default)

    @property
    def login_url(self) -> str:
        return f"{self.base_url}{self.login_path}"

    @property
    def username(self) -> str:
        return os.getenv(self.username_env, self.username_default)

    @property
    def password(self) -> str:
        return os.getenv(self.password_env, self.password_default)


MATTERMOST = TargetProfile(
    name="mattermost",
    display_name="Mattermost",
    stack_label="v9.x · Docker · PostgreSQL",
    base_url_env="MM_URL",
    base_url_default="http://localhost:8065",
    login_path="/login",
    login_id_selectors=_MM_LOGIN_ID_SELECTORS,
    password_selectors=_MM_PASSWORD_SELECTORS,
    submit_selectors=["button#loginButton", "button[type='submit']"],
    username_env="MM_USERNAME",
    username_default="victima@test.com",
    password_env="MM_PASSWORD",
    password_default="Password123!",
    authenticated_selectors=[".channel-header", "#channelHeaderTitle"],
    supports_fresh_reset=True,
    extra_denylist=[],
    # Exact values blocks/static_scanner.py hardcoded before this existed -
    # kept identical here so Mattermost's own B3 behavior doesn't change at
    # all, only NaViQ gains a real scan config of its own.
    source_dir="mattermost-src/mattermost",
    source_extensions=(".go", ".ts", ".tsx", ".js", ".jsx"),
    source_exclude_dirs=frozenset({"node_modules", "vendor", "tests", ".git"}),
    source_relevant_dirs=frozenset({"api", "app", "handlers", "store", "services", "auth", "model", "server"}),
)

# Selectors confirmed live against the real local instance during Phase 0
# Task 0.2 (MULTI_TARGET_PLAN.md) — #id_login/#id_password and the
# form-scoped submit button were all verified working end to end. The
# submit selector is deliberately scoped to `form[action='/login/']`: a
# page-wide `button[type='submit']` matches the i18n language-switcher
# button first (it appears earlier in the DOM on every NaViQ page), which
# is exactly the bug Task 0.2's exploration script hit before this was
# narrowed down.
NAVIQ = TargetProfile(
    name="naviq",
    display_name="NaViQ",
    stack_label="Django · SQLite dev server",
    base_url_env="NAVIQ_URL",
    base_url_default="http://127.0.0.1:8001",
    login_path="/login/",
    login_id_selectors=["input#id_login", "input[name='login']"],
    password_selectors=["input#id_password", "input[name='password']"],
    submit_selectors=["form[action='/login/'] button[type='submit']"],
    username_env="NAVIQ_USERNAME",
    username_default="siftpipe_test",
    password_env="NAVIQ_PASSWORD",
    password_default="",
    authenticated_selectors=["a[href='/logout/']"],
    # True per the Phase 4 decision already recorded in MULTI_TARGET_PLAN.md
    # (a "fresh reset" for the local NaViQ instance is just wiping db.sqlite3
    # + migrate + reseed) — the actual fresh_reset() equivalent is Task 4.1,
    # not built yet. --mode fresh against --target naviq fails loudly until
    # then instead of silently reusing Mattermost's Docker reset.
    supports_fresh_reset=True,
    # Real MercadoPago/PayPal payment infrastructure (MULTI_TARGET_PLAN.md's
    # "Prerequisites" section) — /webhooks/ (webhook receivers) and any
    # /downloads/<slug>/buy/ (real purchase flow) must stay out of B4's
    # crawl and B7's injection, even against the local instance. "/buy/" is
    # deliberately the substring (not "/downloads/" wholesale) — the rest
    # of /downloads/ is an ordinary product listing, legitimate crawl
    # surface.
    extra_denylist=["/webhooks/", "/buy/"],
    # Real gap found 2026-08-10: B3 never ran against NaViQ at all - not
    # just the wrong path, the wrong tech stack. Mattermost's scan config
    # (.go/.ts/.tsx/.js/.jsx under Go-style dir names) matches zero files in
    # a Django project; NaViQ's real application code is .py, spread across
    # per-app directories (users/, blog/, evaluation/, ...) that don't
    # follow Mattermost's api/handlers/store naming convention at all, so
    # source_relevant_dirs stays None - no directory-name filter, just
    # extension + exclude. source_exclude_dirs keeps this out of NaViQ's own
    # real Python venv living inside the source tree
    # (naviq-src/naviq/.venv310) and Django's generated migrations - neither
    # is hand-written application code.
    source_dir="naviq-src/naviq",
    source_extensions=(".py",),
    source_exclude_dirs=frozenset({"node_modules", "vendor", "tests", ".git", ".venv310", "__pycache__", "migrations"}),
    source_relevant_dirs=None,
)

TARGETS = {p.name: p for p in (MATTERMOST, NAVIQ)}
DEFAULT_TARGET = "mattermost"


def get_target(name: str = DEFAULT_TARGET) -> TargetProfile:
    try:
        return TARGETS[name]
    except KeyError:
        raise ValueError(f"Unknown target {name!r}. Available: {', '.join(sorted(TARGETS))}")
