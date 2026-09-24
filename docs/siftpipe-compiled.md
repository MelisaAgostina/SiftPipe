# SiftPipe — Compiled Reference

Source material for the thesis, compiled from documents that are being
retired from `docs/` once their unique content is captured here (see
Sources at the end). Content that already has a permanent home in
`fixes.txt` (the session-by-session bug/fix log) or in
`docs/containerize-siftpipe-design.md` (the containerization architecture
spec, which stays in `docs/` unchanged) is not repeated — this document
holds only what was unique to the retired files.

## 1. Architecture and scope

### Multi-target design

SiftPipe runs its full B1–B9 pipeline against either of two independently
authorized targets — Mattermost and NaViQ — through a `TargetProfile`
abstraction (`blocks/targets.py`) rather than hardcoded, Mattermost-only
values. Each profile carries its own selectors, credentials, static-scan
scope (extensions/directories per target's real tech stack — Go/TypeScript
for Mattermost, Python/Django for NaViQ), and a `supports_fresh_reset`
flag. Every pipeline block reads its target through this profile: B3's
static scanner, B4's crawl, B7's login/injection, and B1's environment
reset all dispatch on `target.name` instead of assuming Mattermost.
Results, screenshots, and videos are namespaced per target
(`results/{target}_{block}.json`, `results/dynamic/{target}/`,
`results/videos/{target}/`) via one shared `result_path()` helper, so two
targets run back to back never overwrite each other's output.

**Deliberate scope boundary (Approach A, not Approach B):** this is *not*
a multi-tenant product where any user can add any site. Explicitly out of
scope: user accounts, sign-up, per-user credential storage, billing/quota,
a UI for adding an arbitrary third site, domain-ownership verification, or
a third target. Two authorized targets is the proof of generalization;
more is a separate, later decision. The frontend's target picker is a
closed 2-item set, deliberately not a free-text field — that's the one
line that would turn this into the broader product. A pluggable LLM
provider was also explicitly kept off this roadmap as an unrelated
concern.

**Why local, disposable instances, never a live/production target:**
NaViQ's real source includes a live MercadoPago/PayPal payment
integration processing real payments, and NaViQ's own core feature calls
paid third-party AI APIs (OpenAI/Claude/Gemini). Both are reasons dynamic
testing runs against a local, disposable copy of the real codebase, never
the hosted site — the same discipline `fresh_reset()` already applied to
Mattermost. The vulnerability classes SiftPipe looks for live in
application code identically whether it's running against a hosted
instance or a local one; what a local instance can't catch is anything
specific to the production deployment itself (CDN/WAF configuration),
which was never in scope for the hosted case either. `/webhooks/` and any
`/buy/`-style payment path stay denylisted for dynamic testing regardless
of target.

### Pipeline-run resilience: resume and stop

Two related features let a pipeline run survive interruption without
re-paying for already-completed LLM calls (B3 static analysis and B5
payload generation are the paid steps a restart would otherwise repeat).

**Mid-pipeline resume.** `api.py`'s two separate orchestration functions
collapse into one ordered `PIPELINE_STEPS` list plus one shared driver.
Each block's completion is snapshotted into `run_history`'s `run_blocks`
table incrementally, not only once at the end — so resuming a crashed run
means finding the first step not yet snapshotted and starting there. A
`resumable` column plus a `dismiss_resume()` call lets Fresh Reset
explicitly turn resumability off, giving a discoverable way to start over
instead of a second, competing button. Because `execute_attacks` (B7) and
the shared `ask_llm()` helper both deliberately catch every exception and
record it as a structured result rather than raising, a crash that
actually reaches the resumable-error state is realistically a B3, B4, B5,
B8, or B9 failure — B7's own live-attack execution doesn't produce the
kind of crash this feature resumes from, though the resume mechanism
still benefits B4/B8/B9 failures by skipping a full B3 restart.

**Stop after the current block.** A `pipeline_state["stop_requested"]`
flag, set by `POST /api/run/stop` and read by the pipeline driver's loop
right after each block finishes (before the existing B5→B6 pause check).
A stopped run is marked exactly like a crashed one and resumes through
the identical mechanism above — no separate code path. Stop only takes
effect at a block boundary, never mid-block: interrupting B4's crawl or
B7's attack loop mid-flight isn't supported, since the pipeline driver's
loop only yields control between whole block calls.

### Containerization — implementation decisions beyond the design spec

`docs/containerize-siftpipe-design.md` covers the architecture (5
services, two isolated networks, the sidecar's fixed API surface,
non-root containers, NaViQ's source never baked into an image). Building
it resolved several points that design intentionally left open for
implementation:

- **Non-root UID/GID: `10001`**, not the design's illustrative "e.g. UID
  1000" — chosen specifically because the Playwright base image
  `siftpipe-api` builds from may already claim UID 1000 for a built-in
  account, and 10001 avoids that collision. The same value is used
  consistently across every image the project builds (`siftpipe-api`,
  `sidecar`, `naviq`, `caddy`) for consistency.
- **Caddy's non-root port binding**, left open by the design as "needs
  confirming," resolved with `setcap cap_net_bind_service=+ep` on the
  Caddy binary at build time — the same technique hardened images like
  `nginx-unprivileged` use. No `cap_add:` entry is needed in Compose,
  because `NET_BIND_SERVICE` is already in Docker's default retained
  capability set for any container; it only needs to not be dropped.
- **Compose's multi-file path-resolution behavior**, worked out
  concretely: when merging multiple `-f` files, Compose resolves every
  relative path against the *first* file's directory, not each file's own
  location. Since `mattermost/docker-compose.yml` must be listed first
  (so its own relative volume paths keep working), any relative path
  written in this project's own `docker-compose.yml` or
  `docker-compose.override.yml` would silently resolve against
  `mattermost/` instead — the wrong directory. The fix: every such path in
  this project's own compose files is an absolute path built from a
  `SIFTPIPE_REPO_ROOT` variable, never a bare `./...`.
- **`SIFTPIPE_REPO_ROOT` and `NAVIQ_SRC_PATH` must be exported in the
  invoking shell**, not just present in a `.env` file — Compose's own
  `${VAR}` interpolation reads the process environment plus at most one
  auto-loaded project `.env` (the first `-f` file's directory,
  `mattermost/.env`), not any other file. `./deploy.sh` exports both on
  every invocation.
- **The sidecar's non-root/Docker-socket tension**, named but left
  unsolved by the design, is resolved at container *start*, not build
  time: since the host's Docker-socket group ID varies by machine, a
  root-owned entrypoint script detects the socket's actual GID at
  startup, creates or reuses a matching group, adds the app user to it,
  then drops to that user via `gosu` before running the app.
- **NaViQ's non-root user needs write access to the bind-mounted
  `db.sqlite3`** — solved by chowning the host-side NaViQ checkout to UID
  10001 as a one-time server-setup step, since NaViQ needs Python 3.10
  exactly and its own entrypoint runs migrate → seed → account-creation on
  every container start (not just once), which is what lets the sidecar's
  reset endpoint work at all.

### Security model

Authentication is a single shared passphrase (`SIFTPIPE_ADMIN_PASSWORD`)
compared with a constant-time check, backing a signed session cookie
(Starlette's `SessionMiddleware`, HMAC-signed via `itsdangerous`) — not
per-user accounts, JWTs, or roles. This is a deliberate scope decision,
not an oversight: with a single shared passphrase there is no per-user
account to store, so the server stays stateless — no session table, no
per-visitor row, nothing persisted beyond the signed cookie itself. The
scope fits a single-audience-tier demo box with a defined teardown date,
while still being a defensible answer if a committee member asks how the
deployment was secured, given the thesis's own subject is OWASP
vulnerability detection (including A07, authentication failures). Every
route is gated by construction through a shared `APIRouter` dependency,
not case-by-case — closing a prior gap where only mutating POST routes
carried any protection and every GET route (results, past runs, PDF
reports, logs, status) had none.

Two deployment-specific problems this design has to account for, since
the frontend and backend can live on different registrable domains (not
just different ports of one host, which browsers treat as "same site"):
a plain `SameSite=Lax` cookie is silently not sent cross-domain at all, so
the deployed environment needs `SameSite=None` + `Secure=True` together
(HTTPS-only), switched on the same "are we actually deployed" signal
already used for CORS; and IP-based login rate-limiting breaks behind a
reverse proxy unless the proxy's `X-Forwarded-For` header is explicitly
trusted, since otherwise every visitor appears to share the proxy's own
address, collapsing the rate limiter into one shared bucket.

CSRF protection requires a custom header (`X-Requested-With`) on every
mutating request — closing a path a plain HTML form or image/script tag
could otherwise use, since `SameSite=None` deliberately lets the session
cookie ride along cross-site (required for cross-domain login to work at
all), which is also exactly what a CSRF attack depends on.

**GitHub-native static scanning as a second, independent check.** CodeQL
(via Advanced setup, a custom workflow rather than the default one-click
config) and Dependabot vulnerability/malware alerts run alongside
SiftPipe's own dynamic pipeline — a genuinely different technique
(pattern-matching static analysis over known-bad code shapes and
known-CVE dependency versions) from SiftPipe's own LLM-assisted static
review, dynamic payload generation, and live attack execution, not a
redundant version of it. Dependabot's automatic version-update PRs are
deliberately left off, to avoid an unattended dependency bump landing
mid-thesis-review. Of the 17 alerts this surfaced (9 CodeQL, 8
Dependabot): one real path-traversal vulnerability was found and fixed
(`GET /api/results/{block_name}` built a file path directly from an
unvalidated URL segment, unlike the neighboring `/media`/`/evidence`
routes which already sanitize); most of the rest were confirmed false
positives (a SHA-256 hash used only to normalize input length before a
constant-time comparison, misread as password storage; a hand-rolled path
sanitizer CodeQL doesn't recognize as one); and all 8 Dependabot alerts
trace to dev/build/test tooling that never sees real request traffic,
confirmed by tracing each dependency chain rather than assuming from the
alert label alone.

## 2. Pipeline steps

Blocks with no code in this repository: B0 (top-level orchestration), B2
(analysis-scope definition as a distinct step — folded into B3's own
prompt instead), B11 (review/triage system integration), B12 (extended
persistence/export beyond what B10's PDF report and `run_history` already
provide).

**B1 — environment preparation.** For Mattermost: tear down and rebuild
the Docker stack, wipe bind-mounted Postgres/Mattermost data via a
throwaway Alpine container (needed because the stack's volumes are bind
mounts, not named volumes — `docker compose down -v` alone does nothing
for them), bring the stack back up, bootstrap a System Admin account via
Mattermost's own zero-user bootstrap exception, then seed a test
user/team/channel/post. For NaViQ: wipe the SQLite database, run
migrations, seed a documented set of fixture data, recreate the test
account (NaViQ requires a verified `EmailAddress` row via
`django-allauth`, not just a created user, since email verification is
mandatory), and ensure the Django dev server is running as a managed
subprocess — automated specifically so a juror can operate the whole
pipeline from the frontend with no terminal access.

**B3 — static analysis with an LLM.** Scans up to 10 files per run,
selected by a scoring system (not filesystem order) that weights
path-based security-relevant keywords and content-based signals (request
input access, injection sinks, access-control checks, secrets/config
patterns) built from the same OWASP categories the LLM prompt targets,
while penalizing test scaffolding and dev tooling. Each file is capped at
15,000 characters and sent with line numbers prefixed, so the model cites
real line numbers instead of counting them itself. Findings carry a CWE
ID and OWASP Top 10:2025 category alongside the vulnerability name,
evidence snippet, and confidence — the CWE/category pair is what B9 uses
to correlate against dynamic findings by identifier rather than free-text
label matching.

**B4 — dynamic discovery with Playwright.** Logs into the target, then
performs a same-origin breadth-first crawl from the post-login landing
page (a generic denylist plus a per-target `extra_denylist` — for NaViQ,
payment-related paths stay excluded even locally) to discover forms,
inputs, and endpoints, rather than a fixed, hand-maintained route list.
Each stage (login, crawl, per-route extraction) tracks its own errors
independently, so the run is classified as `failed` (login never worked),
`partial` (login worked but something along the way didn't), or
`complete` — distinguishing a real failure from "discovery genuinely found
nothing more." Records the full discovery session as one video.

**B5 — payload generation.** Builds a target list from B4's discovered
forms/inputs, computes the most relevant static finding's CWE/OWASP
taxonomy for each target (via keyword-overlap matching against B3's
findings — the relevance ranking itself is keyword-based, not taxonomy-
based; the taxonomy tag rides on whatever that search already returns),
passes it to the LLM as a prompt hint, and asks Claude to generate five
payloads per target. Targets with no related static finding get generic,
class-spanning payloads instead.

**B6 — human review.** Two convergent paths — a console prompt or
`POST /api/validate` — both produce the same `validated_payloads.json`
shape B7 consumes directly. The API path accepts an optional reviewer
comment that persists into the run's history and appears both in the live
review UI and when revisiting that run later.

**B7 — dynamic attack execution.** Executes validated payloads against
discovered targets via Playwright, one isolated browser context per
payload (sharing a single login's session state rather than re-logging in
each time), recording a screenshot and video per finding. Captures the
real HTTP response scoped exactly to the submission action itself (not a
fixed sleep or a loose response-listener match), so a genuine timeout is
recorded as an explicit error rather than empty fields indistinguishable
from "nothing happened." Detection is rule-based (SQL error strings,
reflected payload content with real HTML/JS syntax against an
HTML-shaped response, shell error markers, unexpected 401/403s) — this is
a smoke-testing engine, not a full exploitation framework, and makes no
LLM calls of its own. Each finding's CWE/OWASP taxonomy is computed
deterministically from its rule-matched vulnerability class.

**B8 — dynamic result interpretation.** Classifies each B7 attempt as
`confirmed`, `possible`, or `discarded` via an LLM call, but skips the
call entirely (and records `discarded` directly) when B7's own heuristics
found no anomaly at all — a finding with zero rule-based signal reliably
classifies as discarded regardless, so this avoids paying for a foregone
conclusion. Reuses a prior run's valid classification for the same
payload instead of re-classifying unchanged data. CWE/OWASP tags and
media paths are inherited from B7's finding rather than re-derived, since
B8 decides confirmed/possible/discarded, not what vulnerability class the
finding belongs to.

**B9 — static/dynamic correlation.** Matches each dynamic finding against
static findings in priority order: an exact CWE match (deterministic); a
shared OWASP category with a different or missing CWE, resolved by a
single LLM "judge" call grounded in MITRE's real CWE definitions (capped
per run, with prior verdicts cached and reused across runs); a shared
category alone when no judge is available; or, only when neither side has
any usable taxonomy, legacy free-text label matching. Every correlated
result carries a weighted composite score and severity (dynamic evidence
weighted most heavily, then static confidence, then the correlation
tier's own strength) and a plain-language `match_rationale` explaining
which static finding it matched and why — shown as a click-to-expand
detail in the correlation view, particularly useful for a discarded
finding where there'd otherwise be no visible reason for the correlation
decision.

**B10 — per-run PDF report.** A deterministic render over B9's
already-computed, already-persisted results, making no new LLM calls of
its own — the report never reinterprets evidence, only presents it.
Bilingual (English/Spanish), paginated as real PDF pages via headless
Chromium printing (not a simulated page count). Confirmed and
high-severity findings get a full narrative card with evidence and any
screenshot; findings correlated as `POSSIBLE` get a short, evidence- and
rationale-derived explanation instead of a bare table row; a
"Recommendations" section groups confirmed/possible findings by shared
CWE (so repeated instances of the same weakness collapse into one entry)
with general remediation guidance per CWE class, explicitly labeled as a
general template rather than a verified fix. An appendix reproduces
MITRE's own CWE reference definitions for every CWE actually cited in
that run's results — the same grounding text the B9 judge prompt reasons
against.

**B13 — frontend.** A React/TanStack application with one typed query
hook per backend endpoint and one pure mapper function per pipeline
block's data shape, translating each block's real output into a shared UI
finding representation. Live pipeline views (static analysis, discovery,
payload generation, correlation, logs) read real backend state; a
dedicated review tab handles the B6 approval flow; a "Past Runs" tab
reconstructs any historical run's full result set from persisted
snapshots using the same rendering components the live views use, rather
than a separate historical-data code path.

## 3. Problems and solutions worth keeping as narrative record

Most individual bug fixes are recorded in `fixes.txt`'s session log and
aren't repeated here. A few problems are worth keeping as narrative
because of what they reveal about the pipeline's own failure modes, not
just as isolated fixes:

**A silently empty scan can look identical to a clean one.** B3's source
submodule was registered in git with no `.gitmodules` file pointing at a
real URL, so it never actually downloaded — B3 scanned an empty directory
and reported `{"total_scanned": 0, "findings": []}`, which looks
identical in the UI to "scanned everything, found nothing." The same
failure shape recurred with the LLM itself: it would sometimes return a
placeholder "not found" entry (`"line": 0`) instead of an empty array
despite the prompt explicitly forbidding it — a few of these carried
`medium` confidence and would have been saved as real findings had the
code not added a backstop rejecting any finding with no real cited line
number. The general lesson embedded in both fixes: a scanner reporting
zero findings and a scanner that silently scanned nothing are
indistinguishable to a user unless the code explicitly checks for the
difference.

**A detection heuristic reflecting attacker-controlled content back at
itself.** Every one of several dozen completed Mattermost dynamic-testing
runs showed zero confirmed findings despite dozens of raw ones, because
the reflected-XSS detector fired on any payload merely echoed back
verbatim — including SQL-injection and command-injection test payloads,
since a chat application's API legitimately echoes back whatever was
posted. Fixed by requiring the payload to actually contain real HTML/JS
syntax and the response to actually look like HTML rather than a JSON
API body. Found by checking real historical run data against what the
detector should have produced, not by reading the code in isolation.

**A form-filling heuristic tripped by an invisible field.** Submitting a
payload into one field of a multi-field form fails outright if the form's
other required fields are empty, so a sibling-field auto-fill step was
added — which then had to learn to recognize a spam honeypot field kept
off-screen via CSS and `aria-hidden` rather than the more obvious
`type="hidden"`, since naive visibility checks don't catch that, and
filling it would have gotten every payload against that form treated as
bot traffic.

**A cross-domain deployment breaks assumptions that hold identically in
local dev.** Two separate deployment-specific bugs (the `SameSite`
cookie-delivery issue and the reverse-proxy IP-visibility issue described
in the Security section above) exist specifically because a frontend and
backend on different registrable domains behave differently from the same
two services on `localhost` at different ports, which browsers treat as
the same site. Both were found by checking the actual deployment topology
against the authentication design before deploying it, not discovered
live after the fact.

## 4. Results — Objetivo 3: Mattermost CVE validation

Beyond validating the hybrid pipeline against Mattermost as a real-world
case study (a separate, already-established objective), Objetivo 3 is the
thesis's formal requirement to demonstrate that the pipeline's advantage
replicates specifically because Mattermost carries real, documented CVEs
— not just plausible-looking findings against an unmodified, non-vulnerable
instance. Since the project's default Mattermost version has no
documented, disclosed vulnerability available to test against, validation
required deliberately pinning to an older, specifically vulnerable
version for dedicated runs, separate from the version used for the
general pipeline demonstration, then reverting afterward.

**CVE-2023-7113 (channel-mention XSS, Mattermost ≤8.1.6, CWE-79) — not
reproduced.** The advisory describes unsanitized channel-mention display
names enabling markup injection. Pinning the vulnerable version and
creating a channel whose display name was a markup payload confirmed the
advisory's premise server-side (the raw, unescaped name is embedded in
the post's mention data) — but rendering it client-side, tested as both a
channel member and a non-member (forcing the "unknown channel" fallback
path), came back safely HTML-escaped in both cases. Source inspection
confirmed an `escapeHtml()` call applied uniformly regardless of the
display name's origin. Since Mattermost doesn't publish patch diffs for
security fixes, there's no way to confirm whether that call predates the
fix (meaning the real vulnerable surface was something else — channel
header text, search-result highlighting, and notifications were
considered but not tested) or whether the pulled version tag doesn't
reflect the exact historically vulnerable binary. Recorded as an honest
negative result: a plausible, advisory-consistent hypothesis that didn't
hold up under direct, two-context, source-level testing — itself a fair
methodological point about the limits of working from a terse public
advisory without a private patch diff.

**CVE-2025-3611 (System Manager access-control gap, CWE-284) — root
cause confirmed live, with an actual public fix commit to compare
against.** The bug: a role-permission mapping incorrectly bundled
`PermissionViewTeam` alongside the "Team Statistics" reporting permission,
when team-viewing rights should only ever have come from the dedicated
"Teams" permission. Net effect: an administrator who explicitly restricts
Teams access but leaves Team Statistics reporting on doesn't actually
revoke team-viewing rights, because they were never really tied to the
Teams toggle. Confirmed directly on the live affected version — the
freshly seeded, untouched System Manager role's own permission list, read
via the API before touching anything, does contain exactly this
incorrect pairing. Driving the exploit fully end-to-end (a restricted
account actually pulling team data) needs Mattermost's licensed
Enterprise role editor, confirmed blocked both in the UI (a trial-license
upsell) and via the API — obtaining a trial license was considered and
declined, since it would mean sending real account information to
Mattermost's external license server for a supplementary step judged not
worth that trade.

**For the thesis:** CVE-2025-3611 is the stronger result of the two — a
real, disclosed, CVE-numbered vulnerability with its root cause pinpointed
to one exact data structure in one exact upstream commit, independently
confirmed by direct inspection of the live server's own seeded role data,
not by trusting the advisory's prose alone. CVE-2023-7113 stands as an
honest negative result under rigorous testing, not a dismissed one.

**Closing the loop — does the pipeline's own reasoning replicate the
detection, not just manual investigation?** This is the actual Objetivo 3
claim: it's about the pipeline's own behavior, not manual confirmation
that the vulnerability exists. B4/B7 (dynamic testing) structurally can't
reach CVE-2025-3611 at all, since full exploitation needs the licensed
Enterprise role editor already established as unavailable — B3 (static
analysis), needing only source code and not a running licensed instance,
was the one block with a real path to catching it.

## Sources

Compiled from, and superseding as reference material:
`MULTI_TARGET_PLAN.md`, `improvements.md`, `next-steps-before-deployment.md`,
`readme-old.md`, `todo.md`, and the nine `superpowers/plans/` and
`superpowers/specs/` files for mid-pipeline resume, pipeline stop, and the
five-part containerization effort (API, sidecar, NaViQ, compose wiring,
Caddy + deploy script).

`objetivo3_evidence/` (three screenshots and one JSON scan result
supporting the Objetivo 3 section above) was reviewed but not merged —
binary evidence can't be compiled into prose — and was deleted rather than
kept, since the pipeline can reproduce that evidence on demand.
