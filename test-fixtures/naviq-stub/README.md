# naviq-stub

A minimal Django project that satisfies `docker/naviq/entrypoint.sh`'s contract
(installs from `requirements.txt`, runs `migrate`, runs 7 named `seed_*`
management commands, creates a user via `allauth.account.models.EmailAddress`,
serves `GET /` with a 200) without containing any of NaViQ's real,
proprietary code.

It exists so the CI docker-smoke job (`.github/workflows/ci.yml`) can boot
the *entire* compose stack - including the `naviq` service and everything
that `depends_on: naviq (healthy)` - on a public GitHub-hosted runner, where
the real NaViQ checkout (`naviq-src/`, gitignored) is never present.

Point `NAVIQ_SRC_PATH` at this directory to use it:

    NAVIQ_SRC_PATH="$PWD/test-fixtures/naviq-stub" ./deploy.sh up

## What this does NOT verify

This only proves the container plumbing works: image build, venv/permissions,
ALLOWED_HOSTS, the healthcheck's grace period, service ordering. It does
*not* exercise any of NaViQ's real views, models, or seed data - the seed
commands here are no-ops. A boot-smoke pass here is not a substitute for the
live QA pass against real NaViQ.
