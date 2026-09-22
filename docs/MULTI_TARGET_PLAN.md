# SiftPipe → Multi-Target Support (Approach A): NaVi-Q as a second real target

> **Condensed 2026-08-27.** This file originally carried a full phase-by-phase
> implementation log (~1360 lines); most of its checklist-level content is
> already captured in [todo.md](todo.md) §E and its narrative summary in
> readme.md's changelog. What's kept here is what's unique to this file: the
> scoping decisions, and — phase by phase — the goal, what shipped, the real
> bugs found via live testing (not just unit tests), and the test-count
> progression. A full unabridged version of the original is preserved in
> [../docs_backup/MULTI_TARGET_PLAN.md](../docs_backup/MULTI_TARGET_PLAN.md).

Started 2026-08-08. Scoped version of multi-target support: **not** the full
"any user can add any site" product (Approach B, explicitly deferred — see
Non-goals). Gets SiftPipe running against a second real, authorized target —
NaVi-Q (naviq.com.ar) — alongside Mattermost, via a per-target config profile
instead of hardcoded `MM_*` values, so the project can honestly claim
"designed to generalize, validated against two real targets."

**Supersedes** `todo.md` §D's original "multi-target support — out of scope"
line — correct when written, deliberately re-opened for this narrower
version.

## Non-goals (explicitly out of scope for this plan)

- User accounts, sign-up, per-user credential storage, billing/quota.
- A UI for a random user to add an arbitrary third site themselves.
- Domain-ownership verification / consent-gating workflow.
- A third target — two is the proof; more is a different decision later.
- Pluggable LLM provider (separate roadmap item, unrelated to this).

## Target recon and key open-question resolutions (2026-08-08/09)

Stack: Django + `django-allauth`, Bootstrap 5 + jQuery — server-rendered,
meaningfully simpler than Mattermost's React app (no WebSocket/`networkidle`
issues). Login is a plain POST form (`#id_login`/`#id_password`, standard
Django CSRF), no OAuth/CAPTCHA/MFA. Behind Cloudflare (blocks non-browser
clients, passes real browser UAs — confirmed later with real Playwright).

- **Test credentials**: moot once testing targeted a local instance (see
  Decision below) — a fresh local account (`siftpipe_test`) created directly,
  stored in `.env` the same way as `MM_*`.
- **Source access for B3**: NaviQ's GitHub repo is private; resolved by
  cloning it locally into `naviq-src/naviq` (gitignored, **not** a git
  submodule — a private-repo submodule would silently fail into an empty
  folder for anyone without access, the exact class of bug SiftPipe already
  hit once with `mattermost-src`).
- **Payments app found in source**: `downloads/` is a real MercadoPago/PayPal
  integration, confirmed live and processing real payments through the
  owner's own account — this, plus NaViQ calling real paid AI APIs
  (OpenAI/Claude/Gemini) for its core feature, is *why* dynamic testing
  targets a local instance rather than the live site (see Decision below).
  `/webhooks/` and `/downloads/*/buy/` stay denylisted for local dynamic
  testing regardless (signal-quality reasons locally, safety reasons live).
- **Rules of engagement**: the one item left genuinely open (no answer
  needed once local-instance testing was decided).

## Decision: testing targets a local instance, not the live site (2026-08-08)

The owner didn't want SiftPipe writing to her real database. Rather than
restrict to read-only crawling against production, the plan shifted to a
**local, disposable copy of the real codebase** — the same approach SiftPipe
already used for Mattermost (`fresh_reset()` never touched a hosted instance
either). This isn't a workaround; the vulnerability classes SiftPipe looks
for live in application code, identical whether it's running against
Neon-in-production or SQLite locally. It also sidesteps real paid-API cost
risk from NaViQ's AI-evaluation feature. **Honest limitation recorded**:
anything specific to the production deployment itself (Cloudflare/WAF config)
isn't caught this way — a different discipline than what SiftPipe does, and
it was never testing Mattermost's hypothetical hosted deployment either.

## Phase 0 — Local NaViQ instance setup (done 2026-08-08/09)

Real, working local copy set up end to end before writing any generalized
code: Python 3.10 (NaViQ pins it deliberately post-Django-5.2-upgrade),
dependencies installed into a dedicated venv (two real pin conflicts found
and fixed — UTF-16-encoded `requirements.txt`, a `setuptools` version needing
to satisfy `paypal-server-sdk` while still shipping `pkg_resources`),
migrations applied (`downloads`/payments app migrated cleanly, confirming
NaViQ's own `CLAUDE.md` claim that it's "planning only" is stale), seed
commands run (43 Applications, 5 Criteria, 17 Properties, 4 QualityProfiles,
6 ChartTypes, 12 ExampleCharts — hit the same `UnicodeEncodeError`-on-Windows
bug class already documented in SiftPipe's own `fixes.txt` SESSIONs 2/3, from
a `✔` character Windows `cp1252` can't print). Dev server confirmed working,
test account created, full login round-trip verified with real HTTP
requests.

**Task 0.2 (2026-08-09)** — explored the authenticated area live with
Playwright. One real bug hit and fixed: the first login attempt silently
failed because a page-wide `button[type='submit']` selector matched NaViQ's
*language-switcher* button (which appears earlier in the DOM on every page),
not the actual login button — fixed by scoping to
`form[action='/login/'] button[type='submit']`, a lesson carried into Phase
1/3 (any generic submit-button resolution needs to be form-scoped here, not
page-wide). Findings: `/naviq/` and `/naviq/quality-profiles/` are plain
server-rendered Bootstrap tables B4's generic crawl already handles;
`/naviq/quality-profiles/add/` and `/naviq/create-evaluation/` are genuinely
JS-heavy (dynamic criteria rows, a 3-step wizard with hidden fields populated
by JS, a real file-upload field) — B4/B7 would only ever see the *shell* of
these two forms without dedicated JS-interaction steps, called out explicitly
as a real scope decision rather than a silent gap.

## Phase 1 — Target-profile abstraction (done 2026-08-09)

`blocks/targets.py`: a `TargetProfile` dataclass (selectors, credentials,
`supports_fresh_reset`), concrete `MATTERMOST`/`NAVIQ` instances, and
`get_target(name)`. `main.py` gained `--target`; `api.py` gained
`ACTIVE_TARGET` resolved eagerly at import (fails fast on a typo'd env var).
`--mode fresh`/`POST /api/environment/reset` both refuse loudly for
`target != "mattermost"` at this stage (Phase 4 later made NaViQ's fresh
reset real).

**Regression gate:** 115/115 tests green (up from 113). Live verification hit
one unrelated environment bug: piping `main.py`'s stdin through a
Git-Bash/MSYS `mkfifo` for B6's console pause crashes with `RuntimeError:
input(): lost sys.stdin` — a Windows/shell quirk, not a Phase 1 regression
(confirmed by continuing B6→B9 via an in-process driver instead).

## Phase 2 — B4 discovery generalization (done 2026-08-09)

`blocks/crawler.py` (new): pure, unit-tested link-selection helpers,
replacing Mattermost's old hardcoded 4-path `page_routes` list with a real
BFS crawl from the post-login landing page. `extract_forms()` needed zero
changes.

**Two real bugs found via live runs, not code review:** a failed page
(`/threads`) was being re-discovered and re-attempted every subsequent page
instead of once, since it was only marked "visited" on success — fixed by
marking visited on dequeue, independent of outcome. Against NaViQ, the
`state="visible"` default on `authenticated_selectors` timed out even though
Playwright's own log showed the element existed (present but not on-screen
without further interaction) — fixed by switching to `state="attached"`.

**Results:** Mattermost beat its old-code baseline (13 forms/26 inputs/80
endpoints vs. 5/10/54); NaViQ crawled clean (30 forms/43 inputs, 0 errors).
136/136 tests green (21 new).

## Phase 3 — B7 injection generalization (done 2026-08-09/10, highest uncertainty)

`_login()`/`run_payloads()` in `blocks/dynamic_injector.py` took a `target`
profile; `_is_submission_response()` replaced the Mattermost-only URL-suffix
check with a generic predicate (POST + same-origin + not a static asset) that
turned out to cover both Mattermost's fetch-based API and NaViQ's classic
Django POST-redirect forms with one unified rule, not two. Submission itself
needed generalizing too — the old code unconditionally pressed Enter
(correct only for Mattermost's fieldless chat textbox); a new `_submit()`
tries a real form-scoped submit button first, falling back to Enter.

**Real bugs found live:** `blocks/targets.py` never called `load_dotenv()`
itself (relied on `main.py` having done it first) — silently resolved
`NAVIQ.password` to `""` for any other caller. A `target`/`target_profile`
naming collision was caught before ever running (the per-payload loop already
used `target` for each payload's own label).

**Addenda (2026-08-10):** `/contact/send/`'s multi-required-field form
blocked submission via the browser's own client-side validation before any
request was sent — fixed with `_disable_client_validation()` (sets
`noValidate`), then `_fill_sibling_fields()` (heuristic placeholder values
for a form's other empty fields, no LLM call). Real bug found live: NaViQ's
contact form has a spam honeypot hidden via CSS + `aria-hidden` rather than
`type="hidden"` — Playwright's `is_visible()` doesn't catch that, so a naive
version would've filled it and gotten every payload treated as bot traffic;
fixed by also skipping `aria-hidden="true"` fields. Separately, checking real
historical run data (not just code intent) showed every one of 8 completed
Mattermost runs sitting at `confirmed_findings: 0` despite 17-20 raw findings
each — root cause: `XSS_reflected` fired on any payload merely echoed back
verbatim, including SQLi/command-injection test payloads Mattermost's chat
legitimately echoes in its own JSON response. Fixed with two required gates:
`_looks_like_xss_payload()` (real HTML/JS syntax) and
`_looks_like_html_response()` (response must actually look like HTML, not
JSON).

**Regression gate:** 140/140 after the base phase, 180/180 after both
addenda (9 new for the XSS fix alone, replaying the real historical false
positives as regression tests).

## Phase 4 — B1/environment target-awareness (done 2026-08-09)

Since testing now targets a local NaViQ instance, `supports_fresh_reset`
could be `true` for NaViQ too. `naviq_fresh_reset()` (delete db → migrate →
seed in documented order → recreate test account →
`clear_results_folder()`). One real piece of NaViQ-specific knowledge beyond
the plan's own text: `ACCOUNT_EMAIL_VERIFICATION = 'mandatory'` means a plain
`create_user()` can't log in — allauth also needs a verified `EmailAddress`
row.

**Two real bugs found via a live end-to-end run:** (1) selector-building
treated B4's `"unknown"` sentinel (no `id` attribute) as a truthy real id for
`field_id` while already guarding `field_name` — produced the literal
unmatchable selector `"#unknown"`, making B7 close to non-functional against
NaViQ specifically (most of its fields lack real ids, unlike Mattermost's).
(2) Fixing that revealed 15/20 of B5's generated NaViQ targets were **hidden
fields** (`csrfmiddlewaretoken`, allauth's `next`) — harmless for Mattermost
(no server-rendered CSRF inputs) but systemic for a classic Django site;
fixed by skipping `type == "hidden"` when building form-field targets.

Task 4.3 decided (not implemented) that NaViQ's dev server stays a manual
prerequisite — later superseded once a jury-facing, terminal-free requirement
appeared (see "NaViQ dev-server automation" below).

**Regression gate:** 153/153 tests green (13 new). Both bugs were invisible
from reading the code — found only by running against a target whose forms
don't share Mattermost's habits.

## Interlude — `run_history` target tagging (done 2026-08-10, ahead of Phase 5)

Found by direct observation, not from the task list: `runs` had no `target`
column, so Past Runs couldn't say which target a historical run used. Fixed
with a safe `ALTER TABLE` migration (idempotent, verified against the
project's own real `siftpipe_history.db`); 13 pre-existing rows corrected by
hand using actual session knowledge. `results/` folder per-target separation
(a much bigger change touching most of the codebase's file I/O) was
deliberately deferred here — see its own section below, done later the same
day once it became a visible bug rather than a theoretical one.

## Phase 5 — Frontend target-awareness (done 2026-08-10)

`GET/POST /api/target` (the latter guarded 409 while a run/reset is in
flight); `ACTIVE_TARGET` became a runtime-switchable global instead of
env-var-only; `/api/environment/health`'s `mattermost_up` generalized to
`target_up`. `TopBar.tsx` got a real 2-button picker over a **closed set** of
the 2 known profiles — deliberately not a free-text field, which is the line
that would make this Approach B. `Sidebar.tsx`'s Fresh/Restore toggle became
target-aware (copy, prerequisites).

**Verified live**, not just by reading the diff: clicking "NaViQ" in the
browser actually re-rendered the Sidebar's prerequisite/reset copy, not just
the TopBar pill; a bogus target name returned a real 400. 166/166 tests green
(8 new).

## B3 target-awareness (done 2026-08-10, ahead of Phase 6 — not originally scoped)

B3 had *never* run against NaViQ at all, revealed by a Phase-6 readiness
check. Not just a hardcoded path: `static_scanner.py`'s
extensions/directory filter was tuned to Mattermost's Go/TypeScript stack
(zero overlap with NaViQ's Django/Python), and the file-list cache had no
target in its name — whichever target ran B3 first won the cache forever.
Fixed via per-target `source_dir`/`source_extensions`/`source_exclude_dirs`/
`source_relevant_dirs` on `TargetProfile` (Mattermost's kept byte-identical;
NaViQ's `.py`-only, excluding its real venv and `migrations/`), plus a
target-scoped cache filename.

**Verified against the real source tree**: 119 real `.py` files found, zero
venv/`.go` contamination, 8 genuine findings from the real LLM. 186/186
tests (6 new).

**Addendum — prompt precision (same session):** the A02 prompt didn't
distinguish a literal secret from an env-var read, so
`os.getenv("ANTHROPIC_API_KEY")` (the correct pattern) was flagged
`confidence: high`. Fixed by explicitly requiring a literal value and
forbidding env-var-read patterns; verified against the exact real files that
produced the false positive (both now return `[]`), with a genuine
Stripe-shaped hardcoded key sanity-checked as still caught. The same
verification pass surfaced a second bug: the LLM returning `"line": 0`
"not found" placeholder entries instead of an empty array, 3 of 5 at
`medium` confidence — would have been saved as real findings. Fixed both in
the prompt and as a code-level backstop (`main.py` rejects any finding with
no real line number), since prompt compliance alone isn't reliable. 188/188
tests (2 new).

## NaViQ dev-server automation (done 2026-08-10, ahead of Phase 6 — not originally scoped)

A jury needed to run the full pipeline from the frontend only, no terminal —
a hard blocker against Phase 4's "manual prerequisite" decision (correct for
a developer, wrong for this requirement). `ensure_naviq_server_running()`
(`blocks/environment.py`) pings NaViQ, spawns `manage.py runserver` as a
background subprocess if unreachable, polls until ready — idempotent by
construction (a real HTTP check, not a flag).

**Three real bugs found live while building/verifying this:**
1. The server's log file lived under `results/`, colliding with every
   reset's wipe (`WinError 32`, file in use) — moved outside `results/`.
2. A leaked file descriptor — caught by a unit test's own cleanup failure,
   not by inspection.
3. **Most significant**: the "Run analysis" button gated only on server
   reachability, not on whether the reset itself had finished — a jury could
   click Run while the DB wipe/migrate/reseed was still running in the
   background. Found via live Playwright testing (sampling the button's
   disabled state across the whole reset window), not code review. Fixed by
   also gating on `!envResetting` — a fix that also covers a latent version
   of the same class of bug on the Mattermost side.

Also fixed: the "{target} running" indicator could briefly flash the
*previous* target's cached health status right after switching, since React
Query kept the stale value until refetch — fixed by only trusting `target_up`
when the health response's own `target` field matches the active one.

**Verified live, real subprocess, real HTTP**: cold start, a repeat
idempotent reset, and the full jury-facing flow through a real headless
browser (pick target → Fresh reset → Run button never enabled prematurely
across a ~45s reset window) — zero terminal commands. 195/195 tests (7 new).

## Phase 6 — End-to-end validation (done 2026-08-10)

Ran for real, not just believed working.

**Run 14 (NaViQ, `restore`, 71s)**: `ensure_naviq_server_running()`'s
restore-mode safety net fired for real (server down, started in 12.7s). B3:
119 files found, 10 scanned, 0 findings — every "not found" placeholder
correctly caught by the new filter. B7: all 3 approved targets landed on the
contact form, all got genuine `302`s — live proof `_fill_sibling_fields()`
works in the full pipeline. 0 anomalies (Django auto-escaping); B9 correctly
correlated 0.

**Run 15 (Mattermost, `fresh`, ~2m16s)**: full teardown/rebuild/reseed. B3
found a **genuine real hardcoded secret** (a live Giphy SDK key in
Mattermost's own `default_config.ts`) correctly kept *while* suppressing
several "not found" placeholders on the same file — real proof the A02 fix
discriminates rather than just suppressing. B7: both `post_textbox` XSS
payloads reflected in Mattermost's own JSON response produced **0
anomalies — first live proof against real Mattermost that the
`XSS_reflected` fix actually works**, not just replayed history. B9: 6
`POSSIBLE` correlations, matching the task's own stated expectation.

Full test suite: 195/195 green, confirmed before and after.

## `results/` per-target separation (done 2026-08-10, ahead of Phase 7 — flagged by the user as top priority right after Phase 6)

Running NaViQ then Mattermost back to back (the two Phase 6 runs) made the
deferred Interlude item a live, visible bug: every block wrote to a fixed
`results/{block}.json`, so run 15 silently overwrote run 14's output.
Generalized B3's own earlier fix (target-scoped filenames) to every block via
one shared helper, `result_path()`, threaded through every function that
previously hardcoded a `results/...` path — also extended to B7's
per-target screenshot/video directories (`results/dynamic/{target}/`,
`results/videos/{target}/`), a second real collision found along the way.
`run_history.py`'s `finish_run()` needed a real fix, not just a path swap: it
used to glob *every* JSON file in `results/` regardless of which run it
belonged to, which would have meant a NaViQ run's snapshot silently
absorbing Mattermost's leftover files once both started coexisting on disk.

**Verified against real two-target runs**: ran NaViQ then Mattermost back to
back — both targets' full file sets (JSON, screenshots, videos) coexisted
afterward with zero cross-target overwrite, confirmed both on disk and via
the live API (`GET /api/results` correctly flipped between the two targets'
own `total_executed` counts on switch — the literal symptom reported, now
fixed). 197/197 tests (2 new).

## Past Runs target display (done 2026-08-10, ahead of Phase 7)

Small follow-up: show which target each Past Run used, directly in the list.
Backend already had the data (`list_runs()` already returned `target` per
row); the gap was entirely frontend — `RunSummary`'s TypeScript type didn't
declare the field, so it was silently dropped. Added the field + a badge in
`PastRunsView.tsx`. **Verified live**: all 17 real historical runs show the
correct badge, alternating Mattermost/NaViQ exactly matching each row's
actual `target` column.

## Phase 7 — Docs (done 2026-08-10)

`readme.md` updated (dated changelog entry, per-block Estado updates, test
count 113→197, roadmap item marked superseded-in-part). `fixes.txt` gained
SESSION 8, the condensed technical record of every real bug found across
Phases 0–6 plus the two same-day follow-ups. `todo.md` §D/§E were kept in
sync throughout, not as a separate pass.

---

## Sequencing note

Phases 0→1→2→3→4 are a dependency chain (each needs the one before). Phase 5
(frontend) can start any time after Phase 1, in parallel with 2/3. Phase 6
needs everything before it done for real, not just believed done. Budget the
most uncertainty in Phase 0 (NaViQ's authenticated area could have been
harder than the public pages suggested) and Phase 3 (the response-capture
generalization was genuinely novel work, not a port of existing logic) — both
turned out to be the phases that found the most real bugs, which tracks.
