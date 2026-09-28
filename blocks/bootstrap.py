"""
blocks/bootstrap.py

Process start-up work, as explicit functions instead of statements that run
when a module is imported.

blocks/pipeline.py used to do all of this at import time: read .env, fetch
secrets from AWS SSM, build the Anthropic client, create logs/ and attach the
log handlers. Importing it for any reason (a test that only wanted
MissingConfigError, blocks/auth.py wanting the same class) therefore had those
side effects, and the imports below it needed `# ruff: noqa: E402` because they
had to come after load_dotenv().

Nothing here runs on import. The two entry points that start a process,
api.py and main.py, call load_environment() and configure_logging() once,
explicitly; everything else can be imported freely.
"""

import logging
import os

from dotenv import load_dotenv

from blocks.aws_secrets import load_aws_secrets

REQUIRED_ENV_VARS = ("ANTHROPIC_API_KEY",)

# Relative to the working directory, like results/ and evidence/. Logs live in
# logs/, not results/: fresh_reset()/naviq_fresh_reset() wipe results/ wholesale
# on every environment reset, so a log kept there would vanish with it.
LOG_DIR = "logs"

_environment_loaded = False


class MissingConfigError(RuntimeError):
    """Raised when a required environment variable is missing.

    A plain RuntimeError, deliberately not SystemExit: api.py's async
    startup handler needs a normal Exception (raising SystemExit - a
    BaseException - from inside FastAPI's/anyio's startup task group
    doesn't propagate cleanly; it surfaces as a CancelledError/
    BaseExceptionGroup mess instead of a clean failure - confirmed live
    with a real TestClient before settling on this design). main()'s CLI
    path catches this and converts it to a clean SystemExit itself, so the
    CLI UX (a short message, no traceback) is unchanged.
    """


def validate_required_env_vars():
    """Fail fast on a missing required env var, instead of only surfacing it
    as a crash on the first LLM call, mid-pipeline. Called explicitly from
    main() and from api.py's own startup - so importing the pipeline modules
    (e.g. for tests, which mock ask_llm and never need a real key) stays safe."""
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise MissingConfigError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Set them in .env before running the pipeline."
        )


def load_environment():
    """Reads .env, then backfills whatever is still missing from AWS SSM
    Parameter Store (a no-op locally - see blocks/aws_secrets.py).

    Order matters: the SSM step only fills names that are not already set, so a
    local .env always wins. Must run before anything reads those variables
    (the Anthropic client, the session secret, the admin password). Safe to call
    more than once - only the first call does any work, so a second call can't
    trigger a second SSM round trip."""
    global _environment_loaded
    if _environment_loaded:
        return
    load_dotenv()
    load_aws_secrets()
    _environment_loaded = True


def configure_logging():
    """Attaches the "siftpipe" logger's file (DEBUG) and console (INFO)
    handlers. Replaces main.py's scattered print() calls with real levels,
    written to a file as well as stdout - which matters once this runs
    headless on an EC2 box nobody is watching live. Safe to call more than
    once: handlers are only added if the logger has none yet."""
    logger = logging.getLogger("siftpipe")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return

    os.makedirs(LOG_DIR, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(os.path.join(LOG_DIR, "siftpipe.log"), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
