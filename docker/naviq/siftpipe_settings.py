"""Deployment settings layered over the target's own, without editing its source.

The naviq container is reached by other containers as http://naviq:8001, and Django answers
400 to any Host header not listed in ALLOWED_HOSTS. NAVIQ_BASE_SETTINGS names the target's real
settings module (NaViQ's by default).
"""
import importlib
import os

_base = importlib.import_module(os.environ.get("NAVIQ_BASE_SETTINGS", "naviq_ai.settings"))
globals().update({name: getattr(_base, name) for name in dir(_base) if name.isupper()})

ALLOWED_HOSTS = [*ALLOWED_HOSTS, "naviq"]  # noqa: F821
