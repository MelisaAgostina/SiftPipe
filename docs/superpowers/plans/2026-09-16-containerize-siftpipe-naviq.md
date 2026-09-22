# SiftPipe NaViQ Container Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working Docker image for the `naviq` service whose own image never contains a single byte of NaViQ's real (private, gitignored) source, by moving `blocks/environment.py`'s `naviq_fresh_reset()` sequence — migrate, run the seven documented seed commands, recreate the test account — into the container's own entrypoint script, run fresh on every container start. This is plan 3 of 5 in the containerization effort; the sidecar (plan 2, already written) is what actually calls `docker compose restart naviq` after deleting `db.sqlite3`; compose wiring (bind-mounting the real `naviq-src/naviq/` into this container) is plan 4.

**Architecture:** `python:3.10-slim` (NaViQ pins Python 3.10 exactly, per `naviq-src/naviq/CLAUDE.md`), with `USER appuser` (UID/GID 10001, same numeric choice as plans 1 and 2) set directly in the Dockerfile — unlike the sidecar's runtime GID-detection dance, this doesn't need root-at-startup logic, because the fix here is chowning a directory *this project controls* to a UID *this project already chose*, not adapting to an external host value that varies per machine. The Dockerfile has no `COPY` step touching NaViQ source at all; `naviq-src/naviq/` is bind-mounted read-write into `WORKDIR /app` at container start. Because that real source is private and unavailable for testing this plan standalone, every task here is verified against a small **synthetic fixture Django project** (`docker/naviq/test-fixture/`) that reproduces NaViQ's real shape closely enough to prove the entrypoint's actual logic works — real Django app, real `django-allauth`, the real seven seed-command names, the real `manage.py shell -c` account-creation script (adapted to read secrets from `os.environ` instead of interpolating them into generated Python source, which avoids the injection risk of string-building Python source from untrusted values). The one already-known unresolved risk — the `setuptools>=68.0.0` / `paypal-server-sdk` conflict documented in `next-steps-before-deployment.md`, explicitly flagged there as "not yet re-verified live" — stays exactly that unverified here too, because verifying it requires NaViQ's actual `requirements.txt`, which this plan by design never touches; Task 4 names the concrete follow-up check.

**Tech Stack:** Python 3.10, Django 5.2.16 + `django-allauth` (the fixture's real dependencies, matching NaViQ's own documented versions), `uv` for the documented `setuptools` override recipe.

**Spec:** `docs/containerize-siftpipe-design.md` — primarily §5 (the private-source problem, solved by never baking NaViQ in) and §7 (which `blocks/environment.py` functions move into this container's entrypoint), plus §2 (image role, `python:3.10-slim` base), §10 (non-root + the bind-mount ownership wrinkle), §12 (healthcheck mirrors `_naviq_server_reachable()`). Real logic mirrored verbatim from `blocks/environment.py:307-557` (`NAVIQ_SEED_COMMANDS`, `naviq_reset_plan()`, `naviq_create_test_account()`, `_naviq_server_reachable()`) and the `setuptools` override recipe from `docs/next-steps-before-deployment.md:876-892`.

## Global Constraints

- Base image: `python:3.10-slim` — exact Python 3.10, matching NaViQ's own documented requirement (spec §2)
- Non-root user: UID/GID `10001`, name `appuser`, set via a plain Dockerfile `USER` directive — no runtime privilege-drop dance needed here (contrast with plan 2's sidecar)
- No `COPY` step in `docker/naviq/Dockerfile` may ever reference `naviq-src` or anything under it — the whole point of spec §5 is that this is structurally impossible, not policy
- The real seed commands, in this exact order (from `blocks/environment.py`'s `NAVIQ_SEED_COMMANDS`): `seed_base_elements`, `seed_standard_profile`, `seed_viz_essentials_profile`, `seed_publication_ready_profile`, `seed_narrative_standard_profile`, `seed_chart_types`, `seed_example_charts`
- The account-creation step must set `is_staff=True` and create a `verified=True` `allauth.account.models.EmailAddress` row — a plain `create_user()` alone can't log in, because NaViQ's own settings set `ACCOUNT_EMAIL_VERIFICATION = "mandatory"` (mirrored exactly from `naviq_create_test_account()`'s own docstring)
- Container listens on `0.0.0.0:8001` (not `127.0.0.1` — same reasoning as plan 1: a container's own loopback isn't reachable from outside it)
- The entrypoint runs the full migrate → seed → account-creation sequence on **every** container start, not just once — this is what lets the sidecar's `/naviq/reset` (already built in plan 2: delete `db.sqlite3` → `docker compose restart naviq`) work at all; `blocks/environment.py`'s own seed-command idempotency was already confirmed by hand ("re-run safely after a crash mid-seed")
- `ensure_naviq_server_running()`'s manual "is it up, do I need to start it" polling logic is **not** reproduced here — the entrypoint just runs the server as the container's own foreground process, and `restart: unless-stopped` (plan 4) does that job instead, matching spec §7's "net simplification, not just a relocation"
- This plan's fixture Django project is testing infrastructure only — it is not, and must never become, a stand-in shipped anywhere near a real deploy; it exists solely so this plan's tasks have something real to run against without NaViQ's actual private source

---

### Task 1: Dockerfile, entrypoint skeleton (deps + migrate), minimal fixture app

**Files:**
- Create: `docker/naviq/Dockerfile`
- Create: `docker/naviq/entrypoint.sh`
- Create: `docker/naviq/test-fixture/manage.py`
- Create: `docker/naviq/test-fixture/fixture_project/__init__.py`
- Create: `docker/naviq/test-fixture/fixture_project/settings.py`
- Create: `docker/naviq/test-fixture/fixture_project/urls.py`
- Create: `docker/naviq/test-fixture/fixtureapp/__init__.py`
- Create: `docker/naviq/test-fixture/fixtureapp/models.py`
- Create: `docker/naviq/test-fixture/fixtureapp/migrations/__init__.py`
- Create: `docker/naviq/test-fixture/fixtureapp/migrations/0001_initial.py`
- Create: `docker/naviq/test-fixture/fixtureapp/management/__init__.py`
- Create: `docker/naviq/test-fixture/fixtureapp/management/commands/__init__.py`
- Create: `docker/naviq/test-fixture/fixtureapp/management/commands/seed_base_elements.py`
- Create: `docker/naviq/test-fixture/requirements.txt`

**Interfaces:**
- Consumes: nothing from earlier tasks (first task of this plan)
- Produces: a buildable image tagged `siftpipe-naviq:test`; when run with the fixture bind-mounted at `/app`, it installs the fixture's deps, migrates, runs one seed command, and serves `GET /` → `200 "ok"` on `0.0.0.0:8001` as `appuser` — Tasks 2-4 extend this same entrypoint and fixture

- [ ] **Step 1: Write the fixture's `requirements.txt`**

```
Django==5.2.16
django-allauth
```

(`django-allauth` deliberately unpinned here — this fixture isn't the real deploy artifact, so it doesn't need the same pin rigor NaViQ's actual `requirements.txt` does.)

- [ ] **Step 2: Write the fixture Django project**

`docker/naviq/test-fixture/manage.py`:
```python
#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fixture_project.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

`docker/naviq/test-fixture/fixture_project/__init__.py`: empty file.

`docker/naviq/test-fixture/fixture_project/settings.py`:
```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "fixture-only-not-for-real-use"
DEBUG = True
ALLOWED_HOSTS = ["*"]
SITE_ID = 1

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "fixtureapp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_EMAIL_VERIFICATION = "mandatory"

ROOT_URLCONF = "fixture_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

USE_TZ = True
```

`docker/naviq/test-fixture/fixture_project/urls.py`:
```python
from django.http import HttpResponse
from django.urls import path


def root(request):
    return HttpResponse("ok")


urlpatterns = [path("", root)]
```

- [ ] **Step 3: Write the fixture app with one seed command**

`docker/naviq/test-fixture/fixtureapp/__init__.py`: empty file.

`docker/naviq/test-fixture/fixtureapp/models.py`:
```python
from django.db import models


class SeedRecord(models.Model):
    name = models.CharField(max_length=100, unique=True)
```

`docker/naviq/test-fixture/fixtureapp/migrations/__init__.py`: empty file.

`docker/naviq/test-fixture/fixtureapp/migrations/0001_initial.py`:
```python
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SeedRecord",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
            ],
        ),
    ]
```

`docker/naviq/test-fixture/fixtureapp/management/__init__.py`: empty file.
`docker/naviq/test-fixture/fixtureapp/management/commands/__init__.py`: empty file.

`docker/naviq/test-fixture/fixtureapp/management/commands/seed_base_elements.py`:
```python
from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_base_elements command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="base_elements")
        self.stdout.write(self.style.SUCCESS("seeded base_elements"))
```

- [ ] **Step 4: Write `docker/naviq/entrypoint.sh`**

```sh
#!/bin/sh
set -e

cd /app

echo "setuptools>=68.0.0" > /tmp/overrides.txt
uv pip install --system -r requirements.txt --override /tmp/overrides.txt

python manage.py migrate

for cmd in seed_base_elements; do
    python manage.py "$cmd"
done

exec python manage.py runserver 0.0.0.0:8001
```

(Only `seed_base_elements` runs for now — Task 2 extends this loop to all seven real seed commands once the fixture has all seven to run.)

- [ ] **Step 5: Write `docker/naviq/Dockerfile`**

```dockerfile
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

COPY docker/naviq/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown appuser:appuser /entrypoint.sh

USER appuser

EXPOSE 8001

ENTRYPOINT ["/entrypoint.sh"]
```

- [ ] **Step 6: Build it**

Run (from the repo root):
```bash
docker build -f docker/naviq/Dockerfile -t siftpipe-naviq:test .
```
Expected: exits 0.

- [ ] **Step 7: Prepare the fixture directory's ownership**

The bind-mounted directory has to be writable by UID 10001 inside the container — the exact wrinkle spec §10 names for the real `naviq-src/naviq/` checkout. On a Linux host (or Docker Desktop's Linux VM):
```bash
sudo chown -R 10001:10001 docker/naviq/test-fixture
```
Expected: exits 0. (On native Windows without WSL2 — not the eventual EC2 target — Docker Desktop's file-sharing layer commonly exposes bind-mounted directories as writable by any UID regardless of `chown`; if so, this step is a no-op on this machine specifically, which does not indicate a defect — the real target is Ubuntu 24.04, where this ownership check is load-bearing.)

- [ ] **Step 8: Run it against the fixture and verify**

Run (`$REPO` = your absolute repo root, matching this plan's earlier convention):
```bash
REPO=/absolute/path/to/siftpipe
docker run -d --name naviq-test -p 8001:8001 \
  -v "$REPO/docker/naviq/test-fixture":/app \
  siftpipe-naviq:test
sleep 5
docker logs naviq-test
curl -s http://localhost:8001/
docker exec naviq-test whoami
docker exec naviq-test test -O /app/db.sqlite3 && echo OWNED_BY_APPUSER || echo NOT_OWNED
docker rm -f naviq-test
sudo chown -R "$(id -u)":"$(id -g)" docker/naviq/test-fixture
rm -f docker/naviq/test-fixture/db.sqlite3
```
Expected: `curl` prints `ok`; `whoami` prints `appuser`; `test -O` (checks the file is owned by the effective UID running the check, i.e. `appuser` since `docker exec` runs as the image's `USER`) prints `OWNED_BY_APPUSER`, proving migrations actually succeeded as a non-root write into the bind-mounted fixture directory. The final `chown`/`rm` hand the fixture directory back to your own user and clean up the generated db file so Task 2 starts from a clean fixture.

- [ ] **Step 9: Commit**

```bash
git add docker/naviq/Dockerfile docker/naviq/entrypoint.sh docker/naviq/test-fixture
git commit -m "Add naviq container skeleton: non-root image, entrypoint, minimal Django fixture"
```

---

### Task 2: All seven seed commands, run in documented order every start

**Files:**
- Modify: `docker/naviq/entrypoint.sh`
- Create: `docker/naviq/test-fixture/fixtureapp/management/commands/seed_standard_profile.py`
- Create: `docker/naviq/test-fixture/fixtureapp/management/commands/seed_viz_essentials_profile.py`
- Create: `docker/naviq/test-fixture/fixtureapp/management/commands/seed_publication_ready_profile.py`
- Create: `docker/naviq/test-fixture/fixtureapp/management/commands/seed_narrative_standard_profile.py`
- Create: `docker/naviq/test-fixture/fixtureapp/management/commands/seed_chart_types.py`
- Create: `docker/naviq/test-fixture/fixtureapp/management/commands/seed_example_charts.py`

**Interfaces:**
- Consumes: Task 1's `SeedRecord` model and `siftpipe-naviq:test` image
- Produces: an entrypoint that runs all seven real seed-command names in the exact documented order on every start — Task 3 builds the account-creation step on top of this same entrypoint, after this loop

- [ ] **Step 1: Add the remaining six fixture seed commands**

Each file follows the exact shape of Task 1's `seed_base_elements.py`, one `SeedRecord` name per command:

`docker/naviq/test-fixture/fixtureapp/management/commands/seed_standard_profile.py`:
```python
from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_standard_profile command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="standard_profile")
        self.stdout.write(self.style.SUCCESS("seeded standard_profile"))
```

`docker/naviq/test-fixture/fixtureapp/management/commands/seed_viz_essentials_profile.py`:
```python
from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_viz_essentials_profile command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="viz_essentials_profile")
        self.stdout.write(self.style.SUCCESS("seeded viz_essentials_profile"))
```

`docker/naviq/test-fixture/fixtureapp/management/commands/seed_publication_ready_profile.py`:
```python
from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_publication_ready_profile command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="publication_ready_profile")
        self.stdout.write(self.style.SUCCESS("seeded publication_ready_profile"))
```

`docker/naviq/test-fixture/fixtureapp/management/commands/seed_narrative_standard_profile.py`:
```python
from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_narrative_standard_profile command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="narrative_standard_profile")
        self.stdout.write(self.style.SUCCESS("seeded narrative_standard_profile"))
```

`docker/naviq/test-fixture/fixtureapp/management/commands/seed_chart_types.py`:
```python
from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_chart_types command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="chart_types")
        self.stdout.write(self.style.SUCCESS("seeded chart_types"))
```

`docker/naviq/test-fixture/fixtureapp/management/commands/seed_example_charts.py`:
```python
from django.core.management.base import BaseCommand

from fixtureapp.models import SeedRecord


class Command(BaseCommand):
    help = "Fixture stand-in for NaViQ's seed_example_charts command"

    def handle(self, *args, **options):
        SeedRecord.objects.get_or_create(name="example_charts")
        self.stdout.write(self.style.SUCCESS("seeded example_charts"))
```

- [ ] **Step 2: Extend the entrypoint's seed loop to the real, complete, ordered list**

Modify `docker/naviq/entrypoint.sh` — replace the `for cmd in seed_base_elements; do` line with the full list, in `blocks/environment.py`'s documented order:
```sh
for cmd in seed_base_elements seed_standard_profile seed_viz_essentials_profile \
           seed_publication_ready_profile seed_narrative_standard_profile \
           seed_chart_types seed_example_charts; do
    python manage.py "$cmd"
done
```

- [ ] **Step 3: Rebuild**

Run:
```bash
docker build -f docker/naviq/Dockerfile -t siftpipe-naviq:test .
```
Expected: exits 0.

- [ ] **Step 4: Run it and verify all seven seed records exist**

Run (same `$REPO`/ownership convention as Task 1):
```bash
REPO=/absolute/path/to/siftpipe
sudo chown -R 10001:10001 docker/naviq/test-fixture
docker run -d --name naviq-test -p 8001:8001 \
  -v "$REPO/docker/naviq/test-fixture":/app \
  siftpipe-naviq:test
sleep 5
docker exec naviq-test python manage.py shell -c "
from fixtureapp.models import SeedRecord
names = sorted(SeedRecord.objects.values_list('name', flat=True))
print(names)
"
docker rm -f naviq-test
sudo chown -R "$(id -u)":"$(id -g)" docker/naviq/test-fixture
rm -f docker/naviq/test-fixture/db.sqlite3
```
Expected: prints a list of all seven names — `['base_elements', 'chart_types', 'example_charts', 'narrative_standard_profile', 'publication_ready_profile', 'standard_profile', 'viz_essentials_profile']`.

- [ ] **Step 5: Commit**

```bash
git add docker/naviq/entrypoint.sh docker/naviq/test-fixture/fixtureapp/management/commands
git commit -m "Run all seven NaViQ seed commands, in documented order, on every naviq container start"
```

---

### Task 3: Test-account creation (`django-allauth`, verified email, `is_staff`)

**Files:**
- Modify: `docker/naviq/entrypoint.sh`

**Interfaces:**
- Consumes: Task 2's fully-seeding entrypoint; `django-allauth` already installed via Task 1's `requirements.txt`
- Produces: the entrypoint's final pre-serve step — creates/resets the `NAVIQ_USERNAME`/`NAVIQ_PASSWORD` account with `is_staff=True` and a verified `EmailAddress`, mirroring `naviq_create_test_account()` exactly except for how the secret reaches the generated Python (via `os.environ`, not string-interpolated into source text)

- [ ] **Step 1: Add the account-creation block to the entrypoint, before the final `exec`**

Modify `docker/naviq/entrypoint.sh` — insert this block after the seed-command loop and before `exec python manage.py runserver 0.0.0.0:8001`:
```sh
python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress

User = get_user_model()
username = os.environ.get('NAVIQ_USERNAME', 'siftpipe_test')
password = os.environ['NAVIQ_PASSWORD']
email = f'{username}@example.local'

user, created = User.objects.get_or_create(username=username, defaults={'email': email})
user.email = email
user.set_password(password)
user.is_staff = True
user.save()

EmailAddress.objects.filter(user=user).delete()
EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
print(f'OK: user={user.username} created={created}')
"
```

This reads `username`/`password` from `os.environ` inside the Python process itself, rather than the original `naviq_create_test_account()`'s approach of building the script text with `f"user.set_password({password!r})\n"` — the original is safe too (it runs via `subprocess.run([...], ...)` with an argv list, never a shell, and `!r` correctly escapes the value into valid Python source), but reading `os.environ` directly is simpler here since this script already has to pass through `sh -c` first.

- [ ] **Step 2: Rebuild**

Run:
```bash
docker build -f docker/naviq/Dockerfile -t siftpipe-naviq:test .
```
Expected: exits 0.

- [ ] **Step 3: Run it with real credentials and verify the account**

Run (same `$REPO`/ownership convention as earlier tasks):
```bash
REPO=/absolute/path/to/siftpipe
sudo chown -R 10001:10001 docker/naviq/test-fixture
docker run -d --name naviq-test -p 8001:8001 \
  -v "$REPO/docker/naviq/test-fixture":/app \
  -e NAVIQ_USERNAME=siftpipe_test \
  -e NAVIQ_PASSWORD=test-dummy-password \
  siftpipe-naviq:test
sleep 5
docker exec naviq-test python manage.py shell -c "
from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress
User = get_user_model()
user = User.objects.get(username='siftpipe_test')
print('is_staff:', user.is_staff)
print('password_ok:', user.check_password('test-dummy-password'))
email = EmailAddress.objects.get(user=user)
print('email_verified:', email.verified, 'primary:', email.primary)
"
docker rm -f naviq-test
sudo chown -R "$(id -u)":"$(id -g)" docker/naviq/test-fixture
rm -f docker/naviq/test-fixture/db.sqlite3
```
Expected:
```
is_staff: True
password_ok: True
email_verified: True primary: True
```

- [ ] **Step 4: Verify it's idempotent — restart and confirm no crash, same account**

Run:
```bash
sudo chown -R 10001:10001 docker/naviq/test-fixture
docker run -d --name naviq-test -p 8001:8001 \
  -v "$REPO/docker/naviq/test-fixture":/app \
  -e NAVIQ_USERNAME=siftpipe_test \
  -e NAVIQ_PASSWORD=test-dummy-password \
  siftpipe-naviq:test
sleep 5
docker logs naviq-test
curl -s http://localhost:8001/
docker rm -f naviq-test
sudo chown -R "$(id -u)":"$(id -g)" docker/naviq/test-fixture
rm -f docker/naviq/test-fixture/db.sqlite3
```
Expected: no traceback in `docker logs` (the `get_or_create` + reset-password shape handles an already-existing user and an already-existing `EmailAddress` row cleanly), `curl` still prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add docker/naviq/entrypoint.sh
git commit -m "Create/reset the NaViQ test account with verified email on every naviq container start"
```

---

### Task 4: `HEALTHCHECK` and a full reset-cycle integration test

**Files:**
- Modify: `docker/naviq/Dockerfile`

**Interfaces:**
- Consumes: Task 3's complete entrypoint
- Produces: a Docker-visible health signal for `docker inspect`/plan 4's `depends_on: condition: service_healthy`, and end-to-end proof that the sidecar's already-built `/naviq/reset` flow (plan 2: delete `db.sqlite3` → `docker compose restart naviq`) actually produces a fully reseeded, freshly-authenticated NaViQ instance

- [ ] **Step 1: Add the `HEALTHCHECK` directive**

Modify `docker/naviq/Dockerfile` — add this line after `EXPOSE 8001` and before `ENTRYPOINT`:
```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/', timeout=3).status == 200 else 1)"
```

This is the same shape as `_naviq_server_reachable()` (`blocks/environment.py:445-449`) — a plain HTTP GET against the root URL — now also visible to Docker itself, not just SiftPipe's own polling code. `python`, not `curl`, since this image never installs `curl` (unlike the sidecar, which needed it for the Docker apt-repo setup) and Python is guaranteed present. `--start-period=15s` (longer than plan 1's `10s`) because this container's startup does real work — `uv pip install`, a migration, seven seed commands, and a shell-scripted account creation — before it can serve anything, unlike `siftpipe-api`'s comparatively instant `uvicorn` boot.

- [ ] **Step 2: Rebuild**

Run:
```bash
docker build -f docker/naviq/Dockerfile -t siftpipe-naviq:test .
```
Expected: exits 0.

- [ ] **Step 3: Verify Docker reports it healthy**

Run (same `$REPO`/ownership convention as earlier tasks):
```bash
REPO=/absolute/path/to/siftpipe
sudo chown -R 10001:10001 docker/naviq/test-fixture
docker run -d --name naviq-reset-test -p 8001:8001 \
  -v "$REPO/docker/naviq/test-fixture":/app \
  -e NAVIQ_USERNAME=siftpipe_test \
  -e NAVIQ_PASSWORD=test-dummy-password \
  siftpipe-naviq:test
sleep 20
docker inspect --format='{{.State.Health.Status}}' naviq-reset-test
```
Expected: prints `healthy`.

- [ ] **Step 4: Plant dirty data, simulate the sidecar's `/naviq/reset` flow directly, and confirm a full reseed**

This replays plan 2's `/naviq/reset` sequence (`delete_host_file()` then `compose_restart_service()`) by hand, against this container directly — proving the two plans actually compose correctly without needing the real sidecar image running:
```bash
docker exec naviq-reset-test python manage.py shell -c "
from fixtureapp.models import SeedRecord
SeedRecord.objects.create(name='dirty-leftover-record')
"
docker exec naviq-reset-test python manage.py shell -c "
from fixtureapp.models import SeedRecord
print(sorted(SeedRecord.objects.values_list('name', flat=True)))
"
rm -f docker/naviq/test-fixture/db.sqlite3
docker restart naviq-reset-test
sleep 20
docker inspect --format='{{.State.Health.Status}}' naviq-reset-test
docker exec naviq-reset-test python manage.py shell -c "
from fixtureapp.models import SeedRecord
from django.contrib.auth import get_user_model
print(sorted(SeedRecord.objects.values_list('name', flat=True)))
print(get_user_model().objects.filter(username='siftpipe_test').exists())
"
curl -s http://localhost:8001/
```
Expected: the first shell call's print shows eight names including `dirty-leftover-record`; after deleting `db.sqlite3` and restarting, the health status returns to `healthy`, the seed-record list is back to exactly the real seven names (`dirty-leftover-record` is gone — the file was deleted, not patched), the test account exists again (`True`), and `curl` prints `ok` — the same outcome the sidecar's `/naviq/reset` endpoint produces in the real deployment, reproduced here without it.

- [ ] **Step 5: Clean up**

Run:
```bash
docker rm -f naviq-reset-test
sudo chown -R "$(id -u)":"$(id -g)" docker/naviq/test-fixture
rm -f docker/naviq/test-fixture/db.sqlite3
```

- [ ] **Step 6: Commit**

```bash
git add docker/naviq/Dockerfile
git commit -m "Add HEALTHCHECK to naviq container and verify full reset-cycle integration with plan 2's sidecar flow"
```

---

## Definition of done for this plan

`docker build -f docker/naviq/Dockerfile -t siftpipe-naviq:test .` succeeds; the resulting container runs as `appuser` (not root), successfully migrates and writes to a bind-mounted directory owned by UID 10001; all seven of NaViQ's real, documented seed commands run in order on every container start; the `NAVIQ_USERNAME`/`NAVIQ_PASSWORD` test account is created with `is_staff=True` and a verified email on every start, idempotently; `docker inspect` reports the container `healthy`; a full delete-db-then-restart cycle — exactly what the sidecar's already-built `/naviq/reset` endpoint does — reliably produces a freshly reseeded, freshly authenticated instance. This container is *not yet* wired to the real `naviq-src/naviq/` bind mount, the real sidecar, or `control-net`'s network isolation — that's plan 4. **Two concrete open items this plan deliberately does not close:** (1) the `setuptools>=68.0.0` / `paypal-server-sdk` override recipe (`docs/next-steps-before-deployment.md:876-892`) is carried forward exactly as documented but still marked "not yet re-verified live" there — confirming it works against NaViQ's actual `requirements.txt` requires running this exact entrypoint against the real, private `naviq-src/naviq/` checkout, which only becomes possible once plan 4 wires up the real bind mount; (2) system build packages beyond `build-essential` (e.g. `libpq-dev`, if NaViQ's real dependencies need Postgres client libraries) are unconfirmed against NaViQ's actual `requirements.txt` for the same reason — both are named here explicitly so neither gets silently assumed solved.
