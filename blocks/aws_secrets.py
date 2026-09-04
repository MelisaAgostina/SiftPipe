"""
blocks/aws_secrets.py

Backfills whichever of this project's secrets aren't already set in the
environment by pulling them from an AWS SSM Parameter Store path, instead
of a hand-edited .env on the deployed box - see
docs/next-steps-before-deployment.md's "AWS deployment ease" section for
the full design rationale (SSM over Secrets Manager, the AWS-managed KMS
key, why this only runs when actually deployed).

Deliberately doesn't hardcode which secret names it expects: it just fills
in os.environ for whatever it finds under SIFTPIPE_SSM_PATH that isn't
already set. blocks/pipeline.py's and blocks/auth.py's own
validate_required_env_vars() are what enforce which specific names are
actually required, exactly as they already do for a plain .env - so a
future secret needs no changes here, only an extra parameter under the
same path.

Must be called from blocks/pipeline.py immediately after its own
load_dotenv() - that same module builds its Anthropic client at import
time (`client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))`), so
anything that fills in os.environ any later than that would be too late:
the client would already have permanently baked in an empty key.
"""

import os


class SecretsFetchError(RuntimeError):
    """Raised when SIFTPIPE_SSM_PATH is set but fetching from it fails -
    a plain RuntimeError (not SystemExit) for the same reason
    blocks/pipeline.py's MissingConfigError is one: FastAPI's async startup
    handler needs a normal Exception to fail cleanly, not a BaseException."""


def load_aws_secrets() -> None:
    """
    No-op unless SIFTPIPE_SSM_PATH is set, so a local run never imports
    boto3 or makes a network call - the only signal this checks for
    "are we actually deployed", the same role FRONTEND_ORIGIN already plays
    elsewhere in this project (api.py's CORS/cookie/rate-limiter setup).

    When set, fetches every parameter under that path in one call (fine at
    this project's scale - three secrets, well under a single page) and
    fills in os.environ only for names not already set, so a local .env -
    or anything already exported - always wins. This is purely a fallback
    for the deployed box, which has no .env at all.
    """
    path = os.getenv("SIFTPIPE_SSM_PATH")
    if not path:
        return

    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    try:
        ssm = boto3.client("ssm")
        response = ssm.get_parameters_by_path(Path=path, WithDecryption=True, Recursive=False)
    except (BotoCoreError, ClientError) as e:
        raise SecretsFetchError(f"Failed to fetch secrets from SSM path {path!r}: {e}") from e

    for param in response.get("Parameters", []):
        name = param["Name"].rsplit("/", 1)[-1]
        if not os.getenv(name):
            os.environ[name] = param["Value"]
