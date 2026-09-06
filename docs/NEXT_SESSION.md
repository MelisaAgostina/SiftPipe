# Next Session — Resume Here

One open thread from the 2026-09-04 session. Thread 1 (NaViQ version
update) is resolved — see below. Delete this file once Thread 2 is folded
into `docs/next-steps-before-deployment.md` or resolved.

---

## Thread 1: NaViQ version update — RESOLVED 2026-09-04

Owner's answers: `downloads/` (real MercadoPago/PayPal payment infra) is
off-limits entirely; `navitools/` (new this version) is in scope but
staff-gated (`navitools/decorators.py`'s `not settings.NAVITOOLS_LIVE and
not request.user.is_staff`, identical shape to `downloads/decorators.py`).

What got done:
- `naviq-src/naviq` confirmed **not git-tracked at all** (`naviq-src/` is
  gitignored — intentional, the user can't redistribute a private
  upstream repo through their own). Backed up the old version to
  `naviq-src/naviq_old_backup_2026-09-04.zip` before touching anything,
  since there was no other rollback path.
- Swapped `naviq-src/naviq/` wholesale for the new version, preserving
  `.env` (secrets) and `.venv310` (venv, not shipped in the download).
  No stray `batch_jobs` references survived (checked); login selectors
  and `NAVIQ_SEED_COMMANDS` in `blocks/environment.py` still match
  unchanged.
- `blocks/targets.py`'s `NAVIQ.source_exclude_dirs` now excludes
  `downloads`; `NAVIQ.extra_denylist` is now `["/webhooks/",
  "/downloads/", "/admin/"]` (was `["/webhooks/", "/buy/"]"` — wholesale
  now, not just the purchase sub-path, per the owner's broader off-limits
  call). `/admin/` is in there for a non-obvious reason, see next point.
- `blocks/environment.py::naviq_create_test_account` now sets
  `is_staff=True` on the SiftPipe test account so B4/B7 can reach
  `navitools/`. Important side effect, confirmed live against the running
  dev server: `is_staff` is Django's real admin flag, so it *also*
  unlocks `/downloads/` (same bypass condition) and `/admin/` (Django's
  full CRUD admin — `downloads/admin.py` registers a `PurchaseAdmin`
  action that calls a real Resend API for delivery emails, reachable at
  `/admin/downloads/purchase/`, outside the `/downloads/` prefix). The
  `extra_denylist` entries are what actually keep those out of scope now
  — not the account's permission level, which grants all three.
- New `requirements.txt` pulls in `langgraph`/`langchain` for navitools'
  pipelines (`anthropic` also bumped 0.55.0 → 0.121.0). Plain `pip` choked
  with `resolution-too-deep` on the graph; `uv pip install` resolved it
  but surfaced a real bug in the vendored `requirements.txt`: it pins
  `setuptools==58.1.0` while `paypal-server-sdk==2.3.0` (via
  `apimatic-core`) needs `>=68.0.0` — unsatisfiable as pinned. Worked
  around locally with a `uv --overrides` file (not by editing the vendored
  `requirements.txt`) rather than picking a version by hand; worth
  mentioning to NaViQ's owner since it's their file, not ours.
- Verified end-to-end: `manage.py check` clean, full `naviq_fresh_reset()`
  ran clean (migrations for `downloads`/`navitools` included, all 7 seeds,
  test account), and a live login confirmed `/navitools/`, `/downloads/`,
  and `/admin/` are all `200` for the staff test account — matching the
  denylist reasoning above exactly.

---

## Thread 2: Docker / containerization

**Status: not started. No Dockerfile or docker-compose.yml exist yet.**

### Why now
Per `docs/next-steps-before-deployment.md`'s own stated execution order
(architecture → business logic → UI → i18n → security → *then* package
it), Docker was deliberately sequenced after everything else — and as of
this session, everything else in that list is now checked off, including
the frontend test-coverage backfill (96 new tests this session, 122 total,
TypeScript/lint clean). Docker is next in line by the doc's own logic.

### What's already decided (nothing implemented yet)
- The doc's "highest-leverage item" section already scopes it: a
  Dockerfile for `api.py` (Python + Playwright/Chromium deps) plus a
  `docker-compose.yml` that also brings up Mattermost.
- **Open question not yet resolved:** NaViQ currently runs via a plain
  Python venv (`blocks/environment.py`'s `ensure_naviq_server_running()` /
  `naviq_fresh_reset()` / `NAVIQ_VENV_PYTHON`), not its own container the
  way Mattermost is. Docker work needs to decide: does NaViQ get its own
  service in `docker-compose.yml` too, or does it keep running via a venv
  inside the SiftPipe container/host? Not discussed yet — decide before
  writing the compose file, not while writing it.
- A related, separate decision **is** already recorded in
  `docs/next-steps-before-deployment.md`'s "AWS deployment ease" section:
  the eventual deploy script (pulling new code onto the AWS box and
  restarting) will be a manually-triggered GitHub Actions workflow
  (`workflow_dispatch`), not a plain local script and not auto-deploy on
  push — full reasoning already written up there. Still unimplemented
  (design only), and depends on Docker existing first anyway.

### Also worth remembering (conceptual, discussed but not acted on)
- Once Docker exists, it becomes a snapshot that goes stale on *any*
  dependency or config change (not just code) — a rebuild step to
  remember, not a blocker.
- Any future feature work landing after Docker (a third target, etc.)
  means re-running the Live QA pass against the *packaged* artifact, not
  just re-testing locally — that's the cost of adding scope after
  packaging, matching why the doc sequenced it last in the first place.

### Where to start
`docs/next-steps-before-deployment.md`, section "The highest-leverage
item" (search for "Containerize SiftPipe itself").
