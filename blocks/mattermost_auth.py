"""
blocks/mattermost_auth.py
Login-field selectors shared by B4 (dynamic_analysis.py) and B7
(dynamic_injector.py) — previously hardcoded independently in both, with a
comment in B7 pointing back at B4 as the "source of truth" (so a selector fix
in one place could silently drift from the other), and with zero fallback if
Mattermost ever renamed these specific ids in a version bump. Ordered
most-specific/current first, falling back to more semantic, less
implementation-tied attributes that are more likely to survive a UI change.
"""

LOGIN_ID_SELECTORS = [
    "input[id='input_loginId']",
    "input[name='loginId']",
    "input[autocomplete='username']",
]

PASSWORD_SELECTORS = [
    "input[id='input_password-input']",
    "input[name='password']",
    "input[autocomplete='current-password']",
]


def find_working_selector(page, candidates, timeout=3000):
    """
    Tries each selector in `candidates` in order, returning the first one
    that actually appears within `timeout`. Raises the last exception if
    none do, so callers see a real timeout error rather than a silent
    fallback to a selector that also doesn't exist.
    """
    last_exc = None
    for selector in candidates:
        try:
            page.wait_for_selector(selector, timeout=timeout)
            return selector
        except Exception as e:
            last_exc = e
    raise last_exc
