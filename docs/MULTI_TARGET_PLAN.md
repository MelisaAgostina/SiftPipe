# SiftPipe → Multi-Target Support (Approach A): NaVi-Q as a second real target

Started 2026-08-08. This is the scoped version of multi-target support discussed
and agreed on in chat: **not** the full "any user can add any site" product
(that's Approach B, explicitly deferred — see "Non-goals" below). This plan
gets SiftPipe running against a second real, authorized target — NaVi-Q
(https://www.naviq.com.ar/) — alongside Mattermost, via a per-target config
profile instead of hardcoded `MM_*` values, so the project can honestly claim
"designed to generalize, validated against two real targets" without taking
on a rewrite.

**Supersedes** the line in [todo.md](todo.md) §D ("Multi-target support ... out
of scope on purpose, don't touch") — that call was correct when written, the
scope has since been deliberately re-opened for exactly this narrower version.
`todo.md` is being updated alongside this file.

## Non-goals (explicitly out of scope for this plan)

- User accounts, sign-up, per-user credential storage, billing/quota.
- A UI for a random user to add an arbitrary third site themselves.
- Domain-ownership verification / consent-gating workflow.
- A third target. Two is the proof; more is a different decision later.
- Pluggable LLM provider (separate roadmap item, unrelated to this).

## What we already know about the target (passive recon done 2026-08-08)

- **Stack**: Django + `django-allauth`, Bootstrap 5 + jQuery — traditional
  server-rendered pages, not an SPA. Meaningfully simpler than Mattermost's
  React app (no WebSocket/`networkidle` issues, no client-side landing-page
  interstitial, no JS-hydration timing).
- **Login** (`/login/`): plain POST form, fields `#id_login`
  (`name="login"`) and `#id_password` (`name="password"`), one submit
  button, standard Django CSRF hidden field. No OAuth/social buttons, no
  CAPTCHA, no MFA visible on the page.
- **Infra**: behind Cloudflare. A non-browser HTTP client got a 403; a
  normal browser User-Agent got 200. Real Chromium via Playwright should
  pass the same way — needs verifying for real, not assumed (Phase 0).
- **Known public routes**: `/`, `/naviq/` (the actual tool, behind login),
  `/docs/model-documentation/`, `/docs/naviq-tutorial/`, `/blog/`,
  `/portfolio/`, `/services/`, `/signup/`, `/terms-privacy/`.
- **Unknown**: what `/naviq/` looks like once authenticated — more
  server-rendered forms (easy) or a JS/canvas-heavy visualization UI
  (harder for B4's form discovery). This is Phase 0's main job to answer.

## Open questions to confirm before starting (don't guess these)

- [x] **Test credentials**: moot for the live site now that testing targets
      a local instance instead (see "Local instance, not live site" below) —
      a fresh local account was created directly (`siftpipe_test`), stored as
      `NAVIQ_URL`/`NAVIQ_USERNAME`/`NAVIQ_PASSWORD` in SiftPipe's `.env`
      (same pattern as `MM_USERNAME`/`MM_PASSWORD`). Login verified working
      end to end via a real POST + redirect to `/dashboard/`.
- [x] **Source access for B3**: NaviQ's repo exists on GitHub but is
      private, accessible only from an account not authenticated in this
      session (no `gh` CLI available here either). Resolved: clone it
      locally yourself into `naviq-src/naviq` (gitignored — see
      `.gitignore`), **not** as a git submodule like `mattermost-src`. A
      private-repo submodule would mean anyone who clones SiftPipe without
      NaviQ access (a future session, a thesis evaluator, you on another
      machine) hits `git submodule update --init` failing into a silently
      empty folder — the exact SESSION 6 bug (`mattermost-src` scanning 0
      files with no visible error), except by design instead of by
      accident. Plain gitignored folder avoids that entirely; B3-for-NaviQ
      becomes a documented manual setup step instead of a fragile automatic
      one. **Still needed from you:** the actual `git clone` into that path
      — B4→B9 don't need this at all, only B3 does.
- [ ] **Rules of engagement**: any hours/rate limits the owner wants
      respected, any parts of the site explicitly off-limits (e.g. don't
      touch `/signup/` in a way that spams real emails, don't hit
      `/password/reset/`).
- [x] **Payments app found in the source (2026-08-08)**: `downloads/` is a
      real MercadoPago/PayPal integration — `/webhooks/mercadopago/`,
      `/webhooks/paypal/` (webhook receivers, machine-to-machine only) and
      `/downloads/<slug>/buy/` (real purchase flow). **Confirmed live and
      real** (2026-08-09): the owner has been using the developer's own
      MercadoPago account to process real payments through this app — so
      NaviQ's own `CLAUDE.md` claiming this is "not yet built, planning
      only" is definitely stale, and there's a real financial account
      (the developer's) connected to production. This is why testing
      targets a local instance instead of the live site at all (see the
      "Decision" section below) — `/webhooks/` and `/downloads/*/buy/`
      must never be touched by any *live-site* dynamic testing,
      full stop, not just "excluded by default." Re-verified 2026-08-09
      that no real credentials exist anywhere in the local checkout
      (grepped for token-shaped strings — only fake test fixtures found,
      in a third-party library's own tests and NaviQ's own
      `@override_settings(MP_ACCESS_TOKEN="test-token")`) and that the
      local `.env` has zero payment credentials set. For the **local**
      instance, `/webhooks/` and `/downloads/*/buy/` stay excluded from
      B4/B7 (Task 2.3 denylist) for signal-quality reasons now (predictable
      failures from intentionally-missing local credentials would just be
      noise), not safety — there's no live credential for a local payload
      to reach regardless. Static analysis (B3) is unaffected either way
      and should include `downloads/` — it's genuinely high-value code to
      review (webhook signature verification, the token-based
      `dl/<token>/` download endpoint is a plausible IDOR candidate).

---

## Decision: testing targets a local instance, not the live site (2026-08-08)

The owner does not want SiftPipe writing to her real database — a reasonable,
explicit boundary. Rather than restrict dynamic testing to read-only
crawling against production, the plan shifted to testing a **local,
disposable copy of the real codebase** instead — the same approach SiftPipe
has always used for its primary target (`fresh_reset()` never touched a
hosted Mattermost either, always a local throwaway Docker instance). This
isn't a workaround, it's methodologically the *correct* approach: the
vulnerability classes SiftPipe looks for (injection, XSS, broken access
control, etc.) live in application code, which is identical whether it's
running against Neon-in-production or SQLite-locally. It also sidesteps a
second real concern found along the way: NaViQ's core feature calls real
paid AI APIs (OpenAI/Claude/Gemini) — live-site dynamic testing risked
triggering real API cost on the owner's account, independent of the
database-writes issue.

**One honest limitation, recorded not glossed over**: anything specific to
the *production deployment* (Cloudflare/WAF config, production-only
settings) won't be caught this way. That's infrastructure security posture,
a different discipline than what SiftPipe does — it was never testing
Mattermost's hypothetical hosted deployment either, only ever the local
instance's application logic.

## Phase 0 — Local NaViQ instance: setup (done 2026-08-08)

**Goal:** get a real, working local copy of NaViQ running, seeded, and
confirmed reachable via the same login flow B7 will eventually automate —
before writing any generalized crawl/injection code against assumptions.

- [x] **Task 0.1 (superseded)** — originally "verify Playwright survives
      Cloudflare against the live site." Moot after the local-instance
      decision above — there's no Cloudflare in front of `127.0.0.1:8001`.
- [x] **Python 3.10 installed** (`winget install Python.Python.3.10`) — this
      machine only had 3.12/3.13, and NaviQ's own `CLAUDE.md` is explicit
      that 3.10 is required (deliberately, after a prior Django 5.2 upgrade).
      Same class of problem will recur on the eventual AWS Ubuntu box —
      noted for `AWS_HOSTING_TODO.md` once local setup is fully proven.
- [x] **Dependencies installed** into `naviq-src/naviq/.venv310`, with two
      real conflicts found and fixed (not present in the original
      `requirements.txt` pin set, which assumed setuptools 58.1.0):
      - `requirements.txt` is UTF-16-encoded (not UTF-8) — installed from a
        filtered UTF-8 copy in scratchpad rather than editing the original.
      - `paypal-server-sdk`'s dependency `apimatic-core` requires
        `setuptools>=68.0.0`, conflicting with the pinned `58.1.0`. Fixed by
        pinning `setuptools==75.6.0` specifically — new enough to satisfy
        that, old enough to still ship `pkg_resources` (needed by
        `django-nested-admin`'s `python-monkey-business` dependency; modern
        setuptools, e.g. 84.x, dropped it and breaks Django startup with
        `ModuleNotFoundError: No module named 'pkg_resources'`).
      - One real Windows-specific stall (not a code issue): pip hung
        silently for 10+ minutes replacing its own in-use `setuptools`
        mid-install. Killed and re-split into "upgrade setuptools alone,
        then install the rest" — resumed cleanly since pip skips
        already-satisfied packages.
- [x] **`.env` written** inside `naviq-src/naviq/` (gitignored, never
      committed): dummy `SECRET_KEY`, `DEBUG=True`, everything
      payment/Postgres-related left unset (safe defaults per NaviQ's own
      `settings.py`). One real gotcha found: `evaluation/automation/
      llm_utils.py` constructs the OpenAI client **at module import time**
      (`client = OpenAI(api_key=...)`), and the SDK now raises immediately
      if the key is falsy — Django couldn't even boot without it. Fixed with
      a dummy, non-functional `OPENAI_API_KEY` (satisfies the constructor,
      any real call still fails safely with no cost). Claude/Gemini clients
      only read their env vars lazily — confirmed by reading both files —
      so those stay unset with no boot impact.
- [x] **Migrations applied** — `downloads` (the payments app) migrated
      cleanly alongside everything else, confirming it's real merged code,
      not the "planning only, no app code exists yet" state NaviQ's own
      `CLAUDE.md` claims (that doc is stale on this point — the actual
      downloaded source has working models/views/migrations for it. Worth
      asking the owner directly whether it's even deployed to the live site
      yet, independent of our local testing).
- [x] **Seed commands run** (`CLAUDE.md`'s documented order) — 43
      Applications, 5 Criteria, 17 Properties, 4 QualityProfiles, 6
      ChartTypes, 12 ExampleCharts, matching `CLAUDE.md`'s own numbers
      exactly. The first four commands crashed on their final `self.stdout.
      write(self.style.SUCCESS(...))` line with `UnicodeEncodeError:
      'charmap' codec can't encode '✔'` — Windows console `cp1252`
      can't print `✔`. Same bug class already documented in SiftPipe's own
      `fixes.txt` (SESSION 2/3) for the exact same reason. Verified the
      actual seeding had already completed before the crash (queried the DB
      directly), then re-ran with `PYTHONIOENCODING=utf-8` for clean output
      — safe since the commands are documented idempotent.
- [x] **Dev server confirmed working end to end**: `manage.py runserver
      127.0.0.1:8001` (localhost-only, matching the "never exposed" treatment
      Mattermost already gets). Local `/login/` form is structurally
      identical to the live site's. Created a local test account
      (`siftpipe_test`), credentials stored as `NAVIQ_URL`/`NAVIQ_USERNAME`/
      `NAVIQ_PASSWORD` in SiftPipe's own `.env` (same pattern as `MM_*`).
      Full login round-trip verified with real HTTP requests: POST to
      `/login/` → 302 → `/dashboard/` → 200, authenticated (username and
      logout link present on the page).

- [x] **Task 0.2 (done 2026-08-09)** — explored the authenticated area with a
      real (throwaway, not committed) Playwright script — login via
      `form[action='/login/'] button[type='submit']`, then visited
      `/naviq/`, `/naviq/quality-profiles/`, `/naviq/quality-profiles/add/`,
      `/naviq/evaluations/`, `/naviq/create-evaluation/`,
      `/account/settings/`, extracting every `<form>` (fields, file inputs,
      enctype) and every link matching `delete|archive|logout|remove` via
      generic DOM querying, screenshotting each page. Script and
      screenshots live in scratchpad only (same "throwaway" status as
      Task 0.1's original curl check — referenced later as the "Phase 0
      throwaway script" in Task 3.1).
      **One real bug hit and fixed along the way**: first login attempt
      silently failed — `page.click("button[type='submit']")` matched the
      *language-switcher* button (`<button type="submit" name="language"
      value="en">`, part of an `/i18n/setlang/` form that appears earlier
      in the DOM than the login form on every page) instead of the actual
      login submit button. Confirmed credentials were never the problem
      (`authenticate()` in a Django shell succeeded first try). Fixed by
      scoping the selector to `form[action='/login/'] button[type='submit']`.
      Worth carrying into Phase 1/3: any generic submit-button resolution
      for NaviQ needs to be form-scoped, not page-wide — a page-wide
      `button[type='submit']` selector is a real trap here, not a
      hypothetical one.
      **Findings, by page** (confirmed via `evaluation/views.py`'s
      `@login_required`/`LoginRequiredMixin` decorators, not just
      observed behavior):
      - `/naviq/` (`naviq_home_view`) and `/naviq/quality-profiles/`
        (`QualityProfileListView`) are **not** login-gated — both loaded
        with no session in the first (login-broken) run.
      - `/naviq/` is mostly static marketing/model-doc content, but has one
        genuinely client-heavy piece: an interactive draggable/clickable JS
        tree diagram ("Elements of the Model", with a "Reset Tree"
        control) — the only non-Bootstrap-CRUD widget found anywhere in the
        authenticated area.
      - `/naviq/quality-profiles/` and `/naviq/evaluations/` ("My
        Evaluations") are plain server-rendered Bootstrap tables — exactly
        the shape B4's generic crawl + `extract_forms()` already handles.
        Each profile row's clone action is a trivial one-hidden-field POST
        form (`/naviq/quality-profiles/<id>/clone/`), easy B7 territory.
      - `/naviq/quality-profiles/add/` ("Create Quality Profile") **is**
        client-heavy: criteria are added to the form via a JS "+ Add"
        dropdown/button (`addCriterionSelect`), a "Distribute Evenly"
        button recalculates nested weight fields client-side, and nothing
        about a real submission is visible in the initial DOM — a naive
        "fill every visible field, click submit" approach (B4/B7's current
        Mattermost-era strategy) would submit a profile with zero criteria,
        not a meaningful test of `parse_and_validate_criterion_data()` /
        `save_criterion_structure()` in `evaluation/views.py`.
      - `/naviq/create-evaluation/` ("Start Evaluation") is the most
        JS-heavy page in the whole authenticated area: a 3-step wizard
        (Visualization → Chart type → Interactivity) inside one
        `<form id="evaluationForm">`, confirmed in
        `templates/naviq/evaluation/create_evaluation.html` — hidden inputs
        `chart_type_id`/`is_interactive`/`example_chart_id` are populated
        by JS as the user clicks through steps, a Bootstrap modal
        ("galleryModal") lets you pick a seeded example chart instead of
        uploading, and there's a live AJAX call to `estimate_duration` for
        the "estimated time" badge. Same "fill-and-submit" problem as the
        quality-profile form, worse: steps 2/3's fields don't exist in the
        DOM at all until step 1's Next button (`step1NextBtn`) is clicked,
        which itself starts disabled (`pointer-events:none`) until JS
        validates step 1.
      - **Real file upload found**: `#id_file` / `name="file"`,
        `type="file"`, on a form with `enctype="multipart/form-data"` (the
        visualization image upload in step 1) — genuine attack surface for
        malicious-file-upload payloads, something Mattermost's current B5/B7
        payload set has never had to target.
      - **Automatic/AI evaluation mode** (a toggle on the same page, "AI
        answers from image") calls into `evaluation/automation/` (real
        OpenAI/Claude/Gemini calls in production). On the local instance
        this fails safely — `OPENAI_API_KEY` is a dummy value (per Phase 0's
        earlier `.env` note) and Claude/Gemini keys are unset — but it's
        worth remembering as a mode that would misbehave differently than
        just "form doesn't submit" if triggered by an automated payload run.
      - `/naviq/evaluation/<id>/question/<n>/` (the actual per-question
        evaluation flow, `question_and_options.html`) was **not** reachable
        this session — the `siftpipe_test` account has zero evaluations,
        and creating one requires completing the JS wizard above, which
        this exploration script didn't attempt (out of scope for a
        DOM-survey pass). Checked its template directly instead: `<form
        method="post" id="evalForm">` with a plain `formaction` override for
        the finish button, **no** `fetch()`/`XMLHttpRequest` anywhere in the
        file — confirms this specific step is a classic full-page
        POST-redirect-GET per question, not fetch-driven. Good news for
        Task 3.2: the "same-origin navigation" capture strategy is the
        right one for this flow specifically (still needs a real walkthrough
        once an evaluation exists, this is template evidence, not a live
        capture).
      - `/account/settings/`: plain server-rendered form
        (first_name/last_name/username + one more field), no surprises.
      - Two `/logout/` links found (sidebar + topbar) on every authenticated
        page — same denylist treatment as Mattermost's `/logout` pattern,
        already covered by Task 2.3's planned generic rule.
      **Expected result — delivered**: B4's *generic same-origin crawl +
      `extract_forms()`* (Phase 2) will work as-is for
      `/naviq/quality-profiles/`, `/naviq/evaluations/`, and
      `/account/settings/` — no NaviQ-specific handling needed there. The
      two evaluation-creation forms (`quality-profiles/add/` and
      `create-evaluation/`) are genuinely NaviQ-specific problems: their
      real attack surface (nested criteria structure; the 3-step wizard's
      hidden fields) isn't present in the DOM without JS interaction B4
      doesn't currently do, so B4/B7 will only ever see the *shell* of
      these two forms unless Phase 2/3 adds JS-interaction steps
      specifically for them — a real scope decision to make explicitly in
      Phase 2/3, not a silent gap. The per-question evaluation flow itself
      looks like ordinary Phase 3 territory (plain POST-redirect-GET,
      matches Task 3.2's second capture strategy) but still needs a live
      walkthrough with a real evaluation to confirm, since it wasn't
      directly exercised this session.

## Phase 1 — Target-profile abstraction (mechanical, low risk)

**Goal:** every place that currently reads `MM_URL`/`MM_TEAM`/`MM_USERNAME`/
etc. reads from a named target profile instead — with zero behavior change
for Mattermost when `target=mattermost`.

- [x] **Task 1.1 (done 2026-08-09)** — `blocks/targets.py`: a
      `TargetProfile` dataclass (`base_url`/`login_url` as properties
      derived from env-var name + default, `login_id_selectors`,
      `password_selectors`, `submit_selectors`, `username`/`password`
      properties, `authenticated_selectors`, `supports_fresh_reset`), plus
      concrete `MATTERMOST` and `NAVIQ` instances and a `get_target(name)`
      lookup that raises a clear `ValueError` on an unknown name. Went with
      dataclasses over JSON files as the plan itself suggested — less code,
      no config-loader needed. Mattermost's profile imports
      `LOGIN_ID_SELECTORS`/`PASSWORD_SELECTORS` directly from
      `blocks/mattermost_auth.py` rather than duplicating them, so there's
      exactly one source of truth. NaViQ's selectors/submit strategy use
      the real values confirmed live during Task 0.2
      (`input#id_login`/`input#id_password`, submit scoped to
      `form[action='/login/'] button[type='submit']` — the page-wide
      `button[type='submit']` trap Task 0.2 hit is called out directly in
      a comment so Phase 3 doesn't rediscover it). NaViQ's
      `authenticated_selectors` uses `a[href='/logout/']`, confirmed
      present on every authenticated page during Task 0.2's crawl.
      `supports_fresh_reset=True` for NaViQ per the Phase 4 decision
      already recorded further down in this doc — the flag reflects the
      intended design, not a claim that Task 4.1's implementation exists
      yet (it doesn't).
- [x] **Task 1.2 (done 2026-08-09)** — `main.py` gained a `--target` flag
      (default `mattermost`), resolved via `get_target()` right after
      argument parsing and printed alongside the existing mode banner.
      `api.py` gained `ACTIVE_TARGET = get_target(os.getenv("SIFTPIPE_TARGET",
      "mattermost"))`, resolved eagerly at import time so a typo'd env var
      fails fast at startup instead of a confusing 500 later. Neither
      B3/B4/B5/B7 branch on the resolved target yet — that's genuinely
      Phase 2/3, confirmed by design, not an oversight. One footgun closed
      proactively rather than left for Phase 4 to discover the hard way:
      `--mode fresh` (main.py) and `POST /api/environment/reset` (api.py)
      both now refuse loudly with a clear message for any
      `target != "mattermost"`, instead of silently running Mattermost's
      Docker reset while claiming to serve NaViQ — verified directly
      (`--mode fresh --target naviq` exits 1 with the explanatory message
      instead of touching Docker).
- [x] **Task 1.3 (done 2026-08-09)** — `blocks/mattermost_auth.py` itself
      is unchanged behaviorally (`find_working_selector()` was already
      generic, exactly as the plan predicted) — its docstring now notes
      it's the source of truth `blocks/targets.py` imports from. New tests
      appended to `tests/test_mattermost_auth.py` (the 3 existing ones
      untouched) confirm NaViQ's profile resolves both `#id_login`/
      `#id_password` and the `name=`-attribute fallback candidates through
      the exact same `find_working_selector()` Mattermost uses — no
      NaViQ-specific resolution logic needed anywhere.

**Regression gate for this phase:** ✅ full test suite green — 115/115 (up
from 113: the 2 new NaViQ-selector tests), confirmed via
`python -m unittest discover -s tests`. Manually verified `--target`
resolution end to end: `main.py`/`api.py` both load the correct profile
(`mattermost`, `naviq`, and a deliberately bogus name → clean `ValueError`),
and the fresh-reset guard rejects `--mode fresh --target naviq` as designed.
The plan's other regression check — a real `python main.py --target
mattermost --mode restore` run completing B3→B9 — was attempted for real
against the live local Mattermost and got B3→B5 to genuinely complete (17
static findings, real Playwright login + discovery, 20 payload targets
generated) before hitting an **unrelated Windows environment bug**: piping
`main.py`'s stdin through a Git-Bash/MSYS `mkfifo` for the B6 console pause
crashes with `RuntimeError: input(): lost sys.stdin` — a native
`python.exe` reading a Windows named pipe backed by MSYS's pty-emulation
layer misfires CPython's console/isatty detection. Not a Phase 1 regression
(B3/B4/B5 all ran correctly first); worth remembering as a real constraint
on this specific OS/shell combination if console-mode automation of B6 is
ever needed again, e.g. for CI. Re-verified B6→B9 execute correctly by
continuing from the already-completed B3–B5 disk output in a single
in-process driver (no stdin redirection) — confirmed B7 was about to
correctly pick up all 20 real targets/100 payloads and begin executing
against live Mattermost exactly as before `--target` existed, then stopped
deliberately partway through (100 live payloads × B8/B9 LLM calls was more
Groq-quota spend than a plumbing check needed) rather than let it run to
completion. The stopped run's orphaned `run_history` row (id 10) was marked
`error` instead of left stuck at `running`. **Net: B1–B5 fully reverified
live; B6 verified via a working equivalent path; B7–B9 verified to start
correctly with real data but not run to completion.** Good enough to call
this phase's behavior-preservation goal met — a full uninterrupted B3→B9
live run against Mattermost is still worth doing before Phase 6's final
validation pass, not urgently before Phase 2.

## Phase 2 — B4 discovery generalization

**Goal:** `discover_attack_surface()` stops assuming Mattermost's
`page_routes` list and works off a generic same-origin crawl instead —
verified against both targets.

- [x] **Task 2.1 (done 2026-08-09)** — `blocks/crawler.py` (new): pure,
      unit-tested helpers (`is_same_origin`, `is_denylisted`,
      `normalize_url`, `select_links_to_visit`) that decide which links to
      follow — same-origin, not denylisted, not already visited, capped at
      a remaining-budget count — separate from the actual Playwright
      navigation, which needs a live page and stays in
      `discover_attack_surface()` (`blocks/dynamic_analysis.py`). The old
      hardcoded `page_routes` list (4 fixed Mattermost paths) is gone,
      replaced by a real breadth-first queue starting from the post-login
      landing page. `extract_forms()` needed zero changes, confirming the
      plan's own prediction.
      **Real regression check, run live against Mattermost twice:** first
      run beat the saved baseline from the old `page_routes` code (5 forms
      / 10 inputs / 54 endpoints across 5 hardcoded pages) with 11 forms /
      22 inputs / 81 endpoints across 11 discovered pages — including real
      message-permalink pages (`/pl/<id>`) the old hardcoded list never
      covered. That run also surfaced a genuine bug: a failed page (`/threads`,
      which never renders `.channel-header`) was getting re-discovered and
      re-attempted on every subsequent page instead of once, since it was
      only marked "visited" on success — 11 wasted 8-second timeouts in one
      run. Fixed by marking a URL visited the moment it's dequeued
      (attempted), independent of outcome, while keeping a separate
      `successful_pages` list for the reported `pages_visited` field. Second
      run post-fix: single `/threads` failure (correct — it genuinely lacks
      that selector), 13 forms / 26 inputs / 80 endpoints, no wasted
      retries. `status` still comes back `"partial"` because of that one
      real, expected limitation — accurate, not a bug.
- [x] **Task 2.2 (done 2026-08-09)** — Ran the same crawl live against
      local NaViQ (`discover_attack_surface(target=NAVIQ)`). First attempt
      failed at login with a real bug: `page.wait_for_selector()`'s default
      `state="visible"` timed out on NaViQ's `authenticated_selectors`
      (`a[href='/logout/']`) even though Playwright's own error log showed
      it *found* 2 matching elements — neither the desktop dropdown copy
      nor the mobile-nav copy is visible without further interaction
      (opening the user menu / a mobile viewport breakpoint). Fixed by
      switching both `authenticated_selectors` waits (login + per-page
      crawl loop) to `state="attached"` — presence in the DOM is genuinely
      all this check needs, not on-screen visibility of that specific
      link. After the fix: `status: "complete"`, zero errors, 14 real pages
      crawled (`/dashboard/`, `/naviq/`, `/naviq/quality-profiles/`,
      `/naviq/evaluations/`, `/naviq/create-evaluation/`,
      `/account/settings/`, `/password/change/`, plus `/`, `/blog/`,
      `/docs/naviq-tutorial/`, `/docs/model-documentation/`, `/portfolio/`,
      `/services/`, `/terms-privacy/` — several of these weren't in Task
      0.2's manual list at all, found by the crawler on its own), 30 forms,
      43 inputs, 0 endpoints (expected — the `/api/v4/` endpoint-sniffer
      stays Mattermost-specific on purpose, see Task 2.1's code comment).
      **Reviewed by hand**: every form's `action` URL checked — no
      `/webhooks/` or `*/buy/` paths anywhere, the real file-upload input
      (`#id_file` on `/naviq/create-evaluation/`) correctly captured
      matching Task 0.2's finding, quality-profile clone forms and
      per-page contact forms all sane. Nothing obviously wrong.
- [x] **Task 2.3 (done 2026-08-09)** — `GENERIC_DENYLIST =
      ["/logout", "/delete", "?logout"]` in `blocks/crawler.py`, plus a new
      `extra_denylist` field on `TargetProfile` (`blocks/targets.py`) —
      empty for Mattermost, `["/webhooks/", "/buy/"]` for NaViQ (deliberately
      just the `/buy/` substring, not all of `/downloads/`, since the rest
      of that path is an ordinary product listing and legitimate crawl
      surface). `DEFAULT_MAX_PAGES = 20`, same conservative starting point
      the plan suggested. `tests/test_crawler.py` (21 new tests, no live
      browser needed): same-origin checks, denylist matching including the
      exact NaViQ webhook/buy-flow URLs from the plan's own prerequisites
      section, relative-href resolution, fragment/mailto/javascript/tel
      skipping, dedup, and — the max-page-cap requirement specifically —
      `select_links_to_visit()`'s budget parameter tested directly (a page
      offering more links than the remaining budget yields exactly
      `budget` of them, in page order, zero budget yields nothing).

**Regression gate for this phase:** ✅ full test suite green — 136/136 (up
from 115: 21 new `blocks/crawler.py` tests). `main.py`/`api.py` both pass
the resolved target through to B4 now (`run_dynamic_discovery(pipeline_results,
target)`), so `--target mattermost` (default) drives Mattermost's crawl and
`--target naviq` drives NaViQ's, with the two real bugs above (the
never-marked-visited retry loop; `state="visible"` vs `state="attached"`)
found and fixed via actual live runs against both targets, not assumed from
reading the code. B3/B7 still don't read `target` — B3 was never in this
plan's scope, B7 is genuinely Phase 3.

## Phase 3 — B7 injection generalization

**Goal:** the highest-uncertainty phase. `_is_submission_response` and the
login flow both currently assume Mattermost's specific shapes.

- [x] **Task 3.1 (done 2026-08-09)** — `_login()` in `blocks/dynamic_injector.py`
      now takes a `target` (defaults to Mattermost), using
      `target.login_url`/`login_id_selectors`/`password_selectors`/
      `submit_selectors`/`authenticated_selectors` exactly like B4's
      Phase 2 login generalization — including the same `state="attached"`
      fix (not the default `"visible"`) for the authenticated-indicator
      wait, since it's the identical NaViQ quirk B4 already hit.
      `run_payloads()` gained a `target_profile` parameter (deliberately
      *not* named `target` — the per-payload loop already uses that name
      for each payload's own semantic label read from
      `validated_payloads.json`, e.g. `"post_textbox"`; reusing it would
      have silently shadowed the profile with a string partway through the
      loop. Caught before ever running anything, not live.).
      **Real bug found live, not from reading the code**: the very first
      live login attempt against NaViQ failed — not a logic bug, but
      `blocks/targets.py` never called `load_dotenv()` itself, relying on
      `main.py` having already called it first (true in real pipeline
      usage, false for any throwaway script importing `blocks.targets`
      directly, including this verification). `NAVIQ.password` silently
      resolved to its `""` fallback instead of the real `.env` value.
      Fixed by calling `load_dotenv()` in `blocks/targets.py` itself
      (idempotent, harmless to call again from `main.py`/`api.py`
      afterwards) — the module doing credential resolution should own
      loading the credentials, not rely on caller order.
      **Confirmed live end to end** via `run_payloads()` itself (not a
      separate throwaway script): real login against NaViQ succeeds,
      lands on `/dashboard/`, `a[href='/logout/']` (the authenticated
      indicator) resolves to 2 real elements as expected.
- [x] **Task 3.2 (done 2026-08-09)** — `_is_submission_response(response,
      base_url)` replaced the Mattermost-only URL-suffix check with:
      method == `"POST"`, same-origin as `base_url` (reusing
      `blocks/crawler.py`'s `is_same_origin()` — one definition, used by
      both B4's crawl and B7's capture now), and not a static-asset
      extension. No target-specific endpoint knowledge needed —
      `page.expect_response()` fires for a navigation's own response too,
      not just XHR/fetch, so the same predicate genuinely covers both
      Mattermost's fetch-based chat API and NaViQ's classic Django
      full-page POST-redirect forms. Confirmed live during Task 0.2 that
      NaViQ's forms are plain POST, not fetch/XHR, so only one capture
      strategy was actually needed — the "OR a same-origin navigation"
      branch this task anticipated turned out to be covered by the same
      unified predicate, not a second one.
      **Submission itself also needed generalizing**, beyond what this
      task's own text named: the old code unconditionally pressed Enter
      after filling a field (correct only because Mattermost's
      `post_textbox` isn't inside a `<form>` with a submit button at all —
      chat submits on Enter by design). A generic `<textarea>` in a Django
      form does *not* submit on Enter. Added `_submit()`: tries a real
      submit button scoped to the injected field's own `<form>` via
      Playwright locator chaining first, falls back to Enter only when
      that resolves to nothing — which is exactly what happens for
      Mattermost's fieldless-form textbox, confirmed by the existing
      fake-browser tests still passing unmodified (the fake test double
      doesn't implement locator chaining, so it naturally falls through to
      the Enter path those tests exercise).
      **Confirmed live, two real forms, two different honest outcomes**:
      - `/contact/send/` (email + name + message, no `novalidate`):
        filling only `message` and clicking Send got blocked by the
        *browser's own* HTML5 required-field validation before any
        network request was even made — a real, correctly-captured
        timeout (`"No matching same-origin POST response observed within
        8s"`), not a capture bug. Confirms the limitation already flagged
        in Phase 0/2's notes: B7 only fills one field per payload, so a
        form with multiple required fields needs more than this phase
        implements to reliably reach the server at all.
      - `/account/settings/` (`<form method="post" novalidate>`,
        confirmed by reading the template directly): filling just
        `first_name` and submitting produced a real, complete capture —
        `status_code: 200`, a genuine non-empty HTML response body,
        `error: null`. Task 3.2's literal bar met. Bonus finding along the
        way: the payload was visibly saved server-side (echoed in the
        page's own "logged in as" sidebar badge in the screenshot) but
        `XSS_reflected` correctly did *not* fire, because Django's default
        template auto-escaping turns `<script>` into `&lt;script&gt;` in
        the rendered HTML — the exact-substring `payload in body` check
        correctly returns `False` for a properly-escaped reflection. A
        true negative, not a missed detection.

      **Addendum (2026-08-10)**: the `/contact/send/` limitation above was
      revisited after watching it happen live in a real (non-headless)
      Chrome window — visibly nothing being sent, not just a log line.
      Fixed with `_disable_client_validation()`: sets `noValidate = true`
      (via `page.evaluate()`) on the injected field's enclosing `<form>`
      before `_submit()` tries to click, scoped the same way the submit
      button lookup already is. Doesn't fabricate valid data for a form's
      other fields — the server can still reject the request — but it
      guarantees the request actually gets sent instead of silently dying
      client-side, which is what B7 exists to observe. **Re-verified live
      against the exact same `/contact/send/` + `message` case that
      originally hit this**: `status_code: 302` this time (previously
      `null`/timeout) — a real server round trip. The screenshot after the
      redirect shows Django's own rejection: *"Something went wrong —
      please try again."* — a genuine, informative captured outcome
      (the server validating and rejecting missing fields) instead of a
      timeout that looked identical to "target didn't respond at all."
      153/153 tests still green (the fake-browser test double doesn't
      implement locator chaining, so `_disable_client_validation()` fails
      closed and falls through exactly like `_submit()`'s own button
      lookup already did for Mattermost's fieldless textbox — no test
      changes needed).

      **Addendum 2 (done 2026-08-10)**: the `noValidate` fix above still
      left `/contact/send/` producing a server-side rejection (Django's own
      "Something went wrong" page) rather than a genuine processed
      submission, because `email`/`name` were still empty — exactly the gap
      `_disable_client_validation()`'s own docstring flagged ("doesn't
      fabricate valid data for the other fields"). Closed it with
      `_fill_sibling_fields()`: walks the injected field's `<form>` and
      fills every other empty input/select/textarea with a plausible
      placeholder (`_guess_placeholder_value()` — simple name/id/placeholder
      keyword + HTML-type heuristics, not an LLM call, so it doesn't compete
      with B5's Groq quota) before `_submit()` runs. Skips hidden/submit/
      button/file fields, only checks *required* checkboxes/radios (leaves
      optional ones alone), and never overwrites a field that already has a
      value.

      **Real bug found live, not hypothetical**: NaViQ's own contact form
      has a spam honeypot (`name="website"`, ordinary `type="text"`, hidden
      via `position:absolute; left:-9999px` + `aria-hidden="true"` rather
      than `type="hidden"`). Confirmed via a live Playwright check that
      Playwright's own `is_visible()` returns `True` for it (off-screen
      positioning isn't part of that check) — a naive "skip by type
      attribute alone" version of this feature would have filled the
      honeypot and gotten every payload against this form silently treated
      as bot traffic by the target, defeating the feature's own purpose.
      Fixed by also skipping any field inside an `aria-hidden="true"`
      ancestor (checked live: `True` for the honeypot) before the
      `is_visible()` check.

      **Verified live, end to end, against the real `/contact/send/` form**:
      filled the `message` field with a real payload
      (`<script>alert(1)</script>`), called `_fill_sibling_fields()`, then
      asserted all four outcomes directly against the live page before
      submitting — `email`/`name` auto-filled (`test@example.com`/`Test
      User`), the `website` honeypot still empty, `message` still holds the
      exact unmodified payload. Submitted and got a real `302` (a genuinely
      processed request, not the earlier "Something went wrong" rejection).
      Mattermost's path re-confirmed as an intentional no-op by inspection
      only (not a fresh Docker run) — `post_textbox` has no enclosing
      `<form>`, already established live in this same phase, and the
      existing fake-browser integration tests (which don't implement
      locator chaining) already prove `run_payloads()` as a whole still
      passes with the new call wired in. 171/171 tests green (5 new,
      covering `_guess_placeholder_value()`'s pure heuristic —
      `_fill_sibling_fields()` itself is Playwright glue, tested live
      instead, same as `_submit()`/`_disable_client_validation()`).

      **Addendum 3 (done 2026-08-10)**: asked directly whether B7 actually
      finds anything interesting, so checked the real historical run data
      instead of just describing the code's intent — `siftpipe_history.db`
      shows every one of the 8 completed real Mattermost runs (ids 1-4,
      6-8) landed at `confirmed_findings: 0` despite 17-20 raw
      `total_findings` each time. Digging into what actually triggered the
      raw anomalies found the `XSS_reflected` rule (`payload in body`, no
      other check) tagging SQLi/command-injection *test* payloads —
      `'SELECT * FROM users WHERE id = 1'`, `"ls -l; echo 'Command
      Injection'"` — as XSS, purely because Mattermost's chat legitimately
      echoes back whatever you post in its own JSON API response. A real,
      current false-positive pattern, not a hypothetical. Fixed with two
      gates, both required before `XSS_reflected` fires:
      `_looks_like_xss_payload()` (the payload itself must contain
      HTML/JS-significant syntax — a SQLi string can't demonstrate XSS just
      by being echoed) and `_looks_like_html_response()` (the response must
      actually look like HTML, not JSON — a `<script>`-shaped payload
      echoed back inside a JSON API confirmation isn't parsed/executed as
      HTML, so it isn't reflected XSS either). `_execute_one()` now also
      captures the response's `Content-Type` header (`result["content_type"]`)
      to feed the second gate, falling back to sniffing whether the body
      starts with `<` when the header is missing (e.g. the fake-browser
      test double). **Verified against real data, not synthetic
      scenarios**: replayed every actual historical B7 finding from runs
      6-8 through the corrected gates — all 3 real false positives that
      were originally flagged now correctly evaluate to `False`, and
      nothing else changes. 180/180 tests green (9 new): the exact two
      real false-positive payloads as regression tests, a genuine
      `<script>` reflected in real HTML as the positive case, that same
      payload reflected inside a JSON API response as the negative case
      Mattermost hits on every single post, plus the pure gate functions
      unit-tested directly.
- [x] **Task 3.3 (done 2026-08-09)** — Checked Django's actual error output
      by reading its real source/templates directly
      (`naviq-src/naviq/.venv310/Lib/site-packages/django/views/...`),
      not assumed: `DEBUG=True`'s `technical_500.html` literally contains
      `Traceback`, `Exception Type:`, `Exception Value:` in its own
      static template text; `DEBUG=False`'s fallback page (confirmed no
      custom `500.html` exists anywhere in `naviq-src`, so Django's own
      hardcoded default applies) renders `<h1>Server Error (500)</h1>`.
      **No new markers needed** — the *existing*, never-Mattermost-specific
      markers (`"traceback"`, `"exception"`, `"server error"`) already
      match both cases exactly as they are today. Documented instead of
      silently trusted: `tests/test_dynamic_injector.py` gained
      `TestDjangoErrorMarkers`, asserting the existing marker list against
      Django's real DEBUG=True and DEBUG=False page text pulled from
      those actual templates.

**Regression gate for this phase:** ✅ full test suite green — 140/140 (up
from 136: new `blocks/dynamic_injector.py` tests for the generalized
predicate + Django markers). Both `main.py`/`api.py` now pass the resolved
target through B7 (`execute_attacks(target)` /
`execute_attacks(ACTIVE_TARGET)`), completing target-awareness for
B4 → B5(payload gen, still Mattermost-agnostic already) → B7 for both
targets. B3 remains the only block that never reads `target` — its static
source scan was out of this plan's scope from the start (see Phase 2's
regression note). This phase did run long, as predicted — not because
`_is_submission_response` needed real per-target custom logic (it didn't;
one unified predicate covered both targets cleanly), but because getting
there required generalizing something the task list didn't originally name
(`_submit()`'s button-vs-Enter strategy) and fixing two real bugs
(`load_dotenv()` ordering; the `target`/`target_profile` naming collision,
caught before it ever ran) that only surfaced from actually running this
against a live NaViQ instance twice.

## Phase 4 — B1/environment target-awareness

**Goal:** since testing now targets a local NaviQ instance (see the decision
above), `supports_fresh_reset` can actually be `true` for NaviQ too — a
"fresh reset" just means wiping the local `db.sqlite3` and re-running
migrate + seed, all steps already proven working in Phase 0. This is a
better outcome than the original plan (NaviQ restore-only against the live
site) and mirrors Mattermost's own `fresh_reset()` shape reasonably closely.

- [x] **Task 4.1 (done 2026-08-09)** — `blocks/environment.py` gained
      `naviq_fresh_reset()` and its helpers: `naviq_delete_db()`,
      `naviq_create_test_account()`, and a pure `naviq_reset_plan()`
      (no filesystem/subprocess access) listing the ordered steps —
      delete db → migrate → the 7 seed commands from NaViQ's own
      `CLAUDE.md`, in its documented order → recreate the test account →
      `clear_results_folder()` (shared with Mattermost's `fresh_reset()`,
      reused rather than duplicated). `PYTHONIOENCODING=utf-8` set on every
      subprocess call, per Phase 0's finding. Account creation needed one
      real piece of NaViQ-specific knowledge beyond the plan's own text:
      `ACCOUNT_EMAIL_VERIFICATION = 'mandatory'` in NaViQ's settings means
      a plain `User.objects.create_user()` can't actually log in — allauth
      also needs a verified `EmailAddress` row. Found by reading NaViQ's
      own `scripts/mark_email_verified.py` and reusing that exact pattern,
      run via `manage.py shell -c` (NaViQ's own documented convention for
      one-off DB scripts).
      **Idempotency verified two ways**: `tests/test_environment.py` (6
      tests) confirms `naviq_reset_plan()` — a pure function — returns an
      identical plan on every call, deletes-before-migrates,
      migrates-before-seeding, and seeds in the exact documented order.
      Separately, `naviq_fresh_reset()` was run **for real, twice in a
      row**, against the live local instance — both runs completed cleanly
      (real migrations, real seed counts matching Phase 0's documented
      numbers: 43 Applications, 5 Criteria, 17 Properties), and a real
      login via B7's own code path succeeded after *each* run, confirming
      the recreated account is genuinely usable, not just "the script
      exited 0." One real, useful finding along the way: deleting
      `db.sqlite3` while the dev server was still running and holding a
      connection to it **worked fine** on Windows — worth knowing, since
      it means a fresh reset doesn't strictly require stopping the server
      first (though the server will error on its next request until
      `migrate` finishes recreating the file).
- [x] **Task 4.2 (done 2026-08-09)** — `main.py`'s `--mode fresh` dispatch
      now branches on `target.name` (`mattermost` → `fresh_reset()`,
      `naviq` → `naviq_fresh_reset()`, anything else → a clear error)
      instead of unconditionally rejecting non-Mattermost targets, and
      `api.py`'s `/api/environment/reset` + `run_environment_reset()` got
      the same dispatch. `--mode restore` needed no target-specific code
      at all — "assume it's already up, don't touch anything" was already
      exactly what the existing generic branch did.
      **Confirmed live**, using `main.py`'s own wrapper functions
      (`run_dynamic_discovery`, `generate_payloads`, `execute_attacks`,
      `analyze_results`, `correlate_results` — the same functions
      `python main.py --target naviq --mode restore` calls, B3 excluded
      deliberately: it's hardcoded to scan `mattermost-src` regardless of
      `--target` and was never in this plan's scope, so including it would
      only have burned real Groq tokens scanning the wrong target's source
      for zero relevant signal): B4 crawled 14 real pages (30 forms, 43
      inputs), B7 executed real payloads against live NaViQ, B8/B9 ran to
      completion. `status: "complete"` end to end.
      **Two real bugs found via this live run, both fixed (with your
      go-ahead on the second)**:
      1. `blocks/dynamic_injector.py`'s selector-building treated B4's
         `"unknown"` sentinel (`extract_forms()`'s marker for "this field
         has no id attribute") as a truthy real id for `field_id`, while
         already correctly guarding against it for `field_name` — an
         inconsistency that produced the literal, unmatchable selector
         `"#unknown"`. All 15 payloads in the first live run failed this
         way. Nearly every NaViQ field lacks an `id` (confirmed in Phase
         2's Task 2.2), so this made B7 close to non-functional against it
         specifically; Mattermost's fields mostly do have real ids, which
         is why this had gone unnoticed. Fixed by extracting the logic
         into a pure `_build_selector()` (5 new tests) with the same
         `!= "unknown"` guard on both `field_id` and `field_name`.
      2. Fixing bug #1 revealed a second, deeper one: with real selectors
         now resolving, 15/20 of B5's generated NaViQ targets turned out
         to be **hidden fields** — `csrfmiddlewaretoken` and allauth's
         `next` field, from the `{% csrf_token %}` + language-switcher
         form NaViQ renders on literally every page.
         `build_dynamic_targets()` (`blocks/generate_payloads.py`) never
         filtered `field_type == "hidden"` when expanding a form into
         per-field targets — harmless for Mattermost (a React SPA with no
         server-rendered CSRF inputs cluttering every page) but systemic
         for a classic Django site like NaViQ, crowding out genuinely
         interesting targets (the contact form's `email`/`message`,
         account settings' `first_name`, etc.) almost entirely. Fixed by
         skipping `type == "hidden"` fields when building form-field
         targets (2 new tests, including one confirming a form made
         entirely of hidden fields — like NaViQ's i18n form — now
         contributes zero targets).
      **After both fixes**: re-ran live: real, correct field selectors
      resolved (no more `"#unknown"`/timeout-on-hidden-field errors); the
      3 auto-approved targets in that run all happened to land on the
      contact form (`email`/`name`/`message`, each individually), which
      hit the *already-known, already-discussed* limitation from Phase 3 —
      one field filled, multiple required fields, no `novalidate`, client-
      side validation blocks the request before it's ever sent. Not a new
      bug — the exact same limitation Task 3.2 already documented and
      that was explicitly deferred rather than fixed, re-surfacing here
      because a different random 3-of-20 sample happened to land on that
      form instead of `/account/settings/`. Phase 3's own live check
      already proved the underlying capture mechanism produces a real,
      non-empty response when the target form doesn't have this
      constraint — this run doesn't contradict that, it just landed on the
      known limitation instead of avoiding it.
- [x] **Task 4.3 (decided 2026-08-09, not implemented)** — B1 does **not**
      take ownership of starting/stopping NaViQ's `manage.py runserver`;
      it stays a manual prerequisite, same as Phase 0 already treated it.
      Reasoning, not just a coin flip: Mattermost's Docker container is
      inherently built for exactly this kind of external orchestration —
      detached mode, a real health-check endpoint, a clean `down`/`up`
      lifecycle. A raw `manage.py runserver` foreground dev process has
      none of that by design, and this very session ran into real,
      concrete friction managing long-lived background processes reliably
      from within a scripted tool environment (see Phase 1's regression-run
      notes) — extending that same fragile pattern to NaViQ's server for
      marginal convenience isn't a good trade. NaViQ's own `CLAUDE.md`
      already documents `manage.py runserver` as the standard local dev
      command with no production/orchestration tooling built around it
      (unlike Mattermost's `docker-compose.yml`, which this project already
      depends on for the AWS demo deployment too). Revisit only if a real
      recurring pain point shows up in practice, not preemptively.

      **Superseded 2026-08-10** — see "NaViQ dev-server automation" below
      (right before Phase 6). Not a reversal of the reasoning above, which
      was correct for its own context (a developer with terminal access);
      a genuinely different requirement showed up instead — a jury running
      the pipeline through the frontend only, with no command line
      available to them at all, for whom "start it manually" isn't friction
      to weigh against Docker's orchestration primitives, it's a hard
      blocker with no workaround. That's exactly the "real recurring pain
      point" this task said to revisit for.

**Regression gate for this phase:** ✅ full test suite green — 153/153 (up
from 140: 6 new `tests/test_environment.py`, 5 new `_build_selector` tests,
2 new hidden-field-filtering tests). `--mode fresh` now genuinely supports
both targets; `--mode restore` needed no changes at all. This phase found
more real, load-bearing bugs than any prior one (2, both fixed) — a good
reminder that Task 4.2's live verification was worth doing for its own
sake, not just as a formality: neither bug was visible from reading the
code, only from actually running it against a target whose forms don't
happen to share Mattermost's habits (real ids on most fields, no
server-rendered CSRF tokens).

---

## Interlude — `run_history` target tagging (done 2026-08-10, ahead of Phase 5)

Not one of the original numbered tasks — found by direct observation while
using the pipeline: `results/` writes to a fixed set of filenames regardless
of target (a NaViQ run's `results/B4_dynamic.json` silently overwrites
whatever Mattermost run wrote there, and vice versa), and separately,
`blocks/run_history.py`'s `runs` table had no `target` column at all, so
the Past Runs list couldn't say which target a historical run used even
though `finish_run()` already snapshots each run's actual JSON output
(no data loss, just no labeling).

Split into two pieces by size, not done together:

- **`run_history` target tagging — fixed now.** Small and a near-prerequisite
  for Phase 5 to be meaningful (no point exposing "active target" in the
  topbar if Past Runs still can't say which target a *historical* run used).
  `runs` gained a `target TEXT` column, migrated safely for a pre-existing
  database via `ALTER TABLE` (guarded against "duplicate column" so it's
  idempotent) rather than assuming a fresh schema — verified against this
  project's own real `siftpipe_history.db`, not just a temp-dir test.
  `start_run(mode, target=DEFAULT_TARGET)` now threads the target through
  from both `main.py` (`target.name` from the resolved `--target` profile)
  and `api.py` (`ACTIVE_TARGET.name`); `list_runs()`/`get_run()` both
  surface it. 5 new tests in `tests/test_run_history.py`, including one
  that builds a `runs` table in the pre-`target`-column shape by hand and
  confirms `_connect()` migrates it without crashing and without losing
  existing rows.
  This project's own 13 pre-existing historical rows were corrected by
  hand afterward, using actual session knowledge (not a blind heuristic
  backfill baked into the migration itself, which would've been wrong for
  some of them): ids 11-13 were this session's own live NaViQ verification
  runs from Phase 4 → `target='naviq'`; ids 1-10 predate any NaViQ work or
  were this session's own Mattermost regression attempts → `target='mattermost'`.
- **`results/` folder per-target separation — deferred.** A much bigger,
  more invasive change: nearly every block writes to a flat
  `results/*.json` path, and `api.py`'s `/media` static mount plus
  `GET /api/results`/`GET /api/results/{block_name}` all assume that flat
  shape. Reworking it into a `results/<target>/` layout (or suffixed
  filenames) touches most of the codebase's file I/O, not a couple of
  lines — deserves its own scoped pass, not a bundled addendum. Not
  urgent: nothing is actually lost today (the `run_history` snapshot
  already protects anything that reached `finish_run()`), it's a
  live-overwrite-between-runs annoyance, not data loss.

## Phase 5 — Frontend target-awareness

**Goal:** the UI stops hardcoding "Mattermost v9.x · Docker · PostgreSQL"
and reflects whichever target is actually active.

- [x] **Task 5.1 (done 2026-08-10)** — `api.py` exposes the active target's
      display name via a new `GET /api/target` (name, `display_name`,
      `stack_label`, `supports_fresh_reset`, plus the `available` list Task
      5.3 needed). Typed in `lib/types.ts` (`ActiveTarget`), consumed by
      `TopBar.tsx` via `useActiveTarget()` instead of the hardcoded
      `"Mattermost v9.x · Docker · PostgreSQL"` string. `TargetProfile`
      itself gained `display_name`/`stack_label` fields (`blocks/targets.py`)
      so the labels have one source of truth instead of being duplicated in
      the frontend.
- [x] **Task 5.2 (done 2026-08-10)** — `Sidebar.tsx`'s Fresh/Restore toggle
      now reads `supports_fresh_reset` off `useActiveTarget()` and disables
      the "Fresh reset" option (forcing `effectiveEnvMode="restore"`) with an
      explanatory note when a target doesn't support it. Both current
      profiles happen to be `True`, so this path has never actually fired
      against a real target yet — logic only, not live-verified, flagged
      honestly rather than claiming a check that wasn't done. Also made the
      prerequisite/error copy target-aware (NaViQ's `manage.py runserver
      127.0.0.1:8001` vs. Mattermost's `docker compose up -d`) since the old
      copy was Mattermost-only text shown regardless of target.
- [x] **Task 5.3 (done 2026-08-10, re-scoped)** — Raised the "no picker
      needed" framing explicitly with the user rather than deciding it
      solo, since this task's own "Expected result" line already
      contradicted its body. Decision: build the picker, but keep it a
      closed set — `TopBar.tsx` renders a 2-button toggle over exactly
      `blocks/targets.py`'s `TARGETS` dict (Mattermost/NaViQ), not a
      free-text "any site" field. That line is what keeps this Approach A,
      not Approach B. `POST /api/target` does the actual switch: rejects an
      unknown name (400) and rejects while a run or env reset is in flight
      (409, mirroring `POST /api/environment/reset`'s existing guard) since
      `ACTIVE_TARGET` is one process-wide global — clears `pipeline_state`/
      `env_state` on a successful switch so the UI doesn't show the
      previous target's stale "completed"/error banner. `/api/environment/
      health`'s `mattermost_up` became a generic `target_up` (Mattermost
      pings its real `/api/v4/system/ping`; anything else falls back to a
      plain GET on `base_url`) — every consumer (`TopBar.tsx`,
      `Sidebar.tsx`, `types.ts`) updated together, no compat shim kept.
      **Expected result, verified live:** started the real API (`uvicorn
      api:app`) and the real Vite dev server, drove it with Playwright —
      `POST /api/target {"name":"naviq"}` over curl actually flips
      `ACTIVE_TARGET` and `/api/environment/health`'s ping target;
      `{"name":"bogus"}` returns a real 400. In the browser, clicking
      "NaViQ" in the TopBar picker actually re-renders the Sidebar's
      prerequisite label, reset-button copy, and manual-start instructions
      to NaViQ's — not just the TopBar pill — confirmed via screenshot, not
      just by reading the diff. Switched back to Mattermost afterward so
      the running backend was left in its default state. 166/166 tests
      green (8 new: `GET`/`POST /api/target`'s success + all three 409/400
      guards, plus `environment_health()`'s target-aware ping path).

## B3 target-awareness (done 2026-08-10, ahead of Phase 6)

Not one of the original numbered tasks — this plan had previously and
deliberately left B3 out of scope entirely ("its static source scan was
never in scope for this plan," per `main.py`'s own comment before this).
Revisited after being asked directly why B3 wasn't running against NaViQ at
all during a Phase 6 readiness check, and confirmed it as a real gap worth
closing, not scope creep into Approach B — NaViQ getting real B3 coverage
is completing an existing target's parity, not adding a new capability
class.

Turned out to be more than a hardcoded path. `blocks/static_scanner.py`'s
`scan_and_save_files()` was already parameterized on `source_dir`, but its
`extensions`/`RELEVANT_DIRS` were hardcoded to Mattermost's actual tech
stack (`.go/.ts/.tsx/.js/.jsx`, directory names like `api`/`handlers`/
`store`) — zero overlap with NaViQ's real Django/Python code. On top of
that, `results/files_list.txt` was a single shared cache with no target in
its name at all: `load_files_list(...) or scan_and_save_files(...)` meant
whichever target ran B3 first got cached forever, and the other target
would have silently kept reusing it.

Fixed by giving `TargetProfile` (`blocks/targets.py`) its own
`source_dir`/`source_extensions`/`source_exclude_dirs`/`source_relevant_dirs`
per target — Mattermost's values kept byte-identical to what was hardcoded
before (zero behavior change there), NaViQ's set to `.py` files, no
directory-name allowlist (`source_relevant_dirs=None` — Django's per-app
layout, e.g. `users/`, `blog/`, `evaluation/`, has no equivalent to
Mattermost's Go-monorepo naming convention, so extension-only filtering is
the honest generalization rather than inventing a fake one), and excluding
NaViQ's own real Python venv living inside its source tree
(`naviq-src/naviq/.venv310`) plus Django's generated `migrations/` — neither
is hand-written application code. `scan_and_save_files()` gained matching
optional parameters (defaulting to Mattermost's exact old hardcoded values,
so any caller that doesn't pass them is unaffected).
`run_static_analysis()` (`main.py`) now takes a `target_profile` — both real
call sites (`main.py`'s own CLI `main()`, `api.py`'s `run_pipeline_until_b6()`)
updated to pass it — and the file-list cache is now target-scoped
(`results/{target}_files_list.txt`), closing the collision.

**Verified against the real source tree, not a synthetic fixture**: ran
`run_static_analysis()` for real against the actual `naviq-src/naviq/`
checkout (not mocked) — found 119 real `.py` files, zero venv
contamination, zero `.go` noise. Scanned the first 10 (`MAX_FILES` cap,
same token-budget guard Mattermost already had) through the real LLM and
got 8 genuine findings saved (medium/high confidence only, same filter as
before) — real per-file evidence like a hardcoded-looking
`ANTHROPIC_API_KEY = os.getenv(...)` pattern and a path-traversal-shaped
`os.path.splitext(os.path.basename(input_path))` call, persisted to the
real (gitignored, so no repo pollution) `results/B3_static.json` and
`results/naviq_files_list.txt`. Individual finding *quality* (the LLM
prompt's own precision/recall) is a separate, pre-existing concern
untouched by this fix — this only proves the pipeline now reaches NaViQ's
real code at all, which it previously never did. 186/186 tests green (6
new: `scan_and_save_files()`'s `relevant_dirs=None` + custom `exclude_dirs`
paths, and `run_static_analysis()`'s target-dispatch + cache-collision
behavior, exercising the real function with `ask_llm`/`time.sleep` patched
out rather than a fake).

**Addendum — B3 prompt precision (done 2026-08-10, same session).** Asked
directly to tighten the "hardcoded secret" false positive flagged above.
Root cause, confirmed against the real code: `OWASP_SCOPE`'s A02
description told the LLM to look for "hardcoded secrets, API keys" with no
distinction between a literal value and an env-var read - so
`ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")` (the textbook
*correct* pattern) got flagged `confidence: high`. Fixed by rewriting A02
to explicitly require a literal string value and explicitly forbid flagging
`os.getenv(...)`/`os.environ[...]`/`.setdefault(...)`/`settings.X` reads.

**Verified against the exact real files that produced the false
positives**, not synthetic cases: replayed `claude_utils.py` and
`gemini_utils.py` through the corrected prompt - both now return `[]`
(previously `confidence: high` "Hardcoded API Key"/"Hardcoded Credentials").
A sanity check with a genuine hardcoded Stripe-shaped key confirms the fix
doesn't just suppress the category wholesale - it's still caught,
`confidence: high`, real CWE-798.

That same real-file check surfaced a second, distinct bug while verifying
the first: `run_batch_evaluations.py` got the false positive fixed, but the
LLM returned "not found" placeholder entries instead of an empty array
(despite the prompt's own existing instruction not to) -
`{"vulnerability": "Broken Access Control", "evidence": "No clear
authorization checks found in the provided code snippet", "line": 0,
"confidence": "medium"}`. Three of five such entries were `medium`
confidence, meaning `main.py`'s pre-existing filter (which only checked for
the literal string `"None"`) would have saved them as real findings. Fixed
two ways: strengthened the prompt with an explicit anti-example (instruction
5, `blocks/static_scanner.py`), and added a code-level backstop in
`main.py` rejecting any finding with no real `"line"` number - a genuine
finding always cites one, "not found" placeholders never do. Prompt
compliance alone can't be guaranteed, so the code-level filter is the one
actually load-bearing here, same defense-in-depth spirit as B8's existing
guard against a malformed `ask_llm()` error payload.

188/188 tests green (2 new: the prompt now explicitly tells the LLM not to
flag env-var secret reads, and the `"line": 0` placeholder-entry filter,
using the exact real bug-shaped response as the fixture).

## NaViQ dev-server automation (done 2026-08-10, ahead of Phase 6)

**Goal:** a jury has to be able to select the target and run the full
pipeline from the frontend only — no command line available to them at
all. Surfaced a real, hard blocker: NaViQ's dev server was still a manual
`manage.py runserver` prerequisite (Phase 4 Task 4.3's deliberate decision,
correct for a developer with terminal access, wrong for this requirement —
see that task's "Superseded" note above).

**`ensure_naviq_server_running()`** (`blocks/environment.py`) — pings
`NAVIQ_URL`; if unreachable, spawns `manage.py runserver 127.0.0.1:8001` as
a background `subprocess.Popen` (stdout/stderr redirected to a log file,
not piped — a long-lived process would otherwise eventually fill an unread
pipe buffer and stall) and polls until it responds or times out (20s — a
local SQLite dev server starts in under a second once the venv resolves,
nothing like Mattermost's Docker+Postgres boot). Idempotent by construction
(a real HTTP check, not a "did we start it" flag), so safe to call on every
reset and every run. Wired into `naviq_fresh_reset()` (the actual UI
on-ramp — "Prepare environment (fresh)" now leaves NaViQ genuinely ready,
not just its database) and as a safety net at the top of
`run_pipeline_until_b6()` (`api.py`) and `main()`'s restore-mode branch
(`main.py`), so it's covered regardless of which mode was picked or
whether "Prepare environment" was clicked at all. `stop_naviq_server()`
is a best-effort cleanup wired to FastAPI's shutdown event — only
terminates a server this process actually spawned, never one a developer
started by hand outside SiftPipe.

**Three real bugs found live while building and verifying this, not
hypothetical:**

1. **Log-file/results-wipe collision.** `NAVIQ_SERVER_LOG_PATH` originally
   lived under `results/` — but the server process keeps that file open
   for as long as it runs, and `naviq_fresh_reset()` calls
   `clear_results_folder()` right after starting it (and on every reset
   after, while the server's still up from before). Hit a real `WinError
   32 "file in use"` on the very first live run. Fixed by moving the log
   outside `results/` entirely, into `naviq-src/` (already fully
   gitignored, never touched by any results/ wipe, so there's no ordering
   dependency to get right regardless of how many times reset runs).
2. **File-descriptor leak.** The parent process's own handle to the log
   file was never closed after `Popen()` — caught by a unit test's own
   temp-dir cleanup failing with a `PermissionError`, not by manual
   inspection. `subprocess.Popen` duplicates the fd for the child, so the
   parent's copy is safe (and correct practice) to close immediately after
   spawning; switched to a `with open(...)` block.
3. **Run button could enable mid-reset.** The most significant one, found
   via live Playwright testing, not code review: `Sidebar.tsx`'s "Run
   analysis" button gated only on `targetUp` (is the server reachable),
   not on whether the reset itself had finished. Because
   `ensure_naviq_server_running()` reports "already up" almost instantly
   on a repeat reset, a jury could click Run while `naviq_fresh_reset()`'s
   DB wipe/migrate/reseed steps were still running in the background —
   starting B3-B9 against a database mid-reset. Fixed by also gating on
   `!envResetting`. This same class of bug likely already existed for
   Mattermost too (its own `wait_for_mattermost()` returns once the
   container pings back, but `create_admin_account`/`run_seed_script`
   still run afterward) — not introduced by this change, but the fix
   covers both targets since `envResetting` isn't target-specific.

**Also found and fixed while live-verifying** (same session, same
Playwright pass): the "{target} running" indicator (`Sidebar.tsx`,
`TopBar.tsx`) could briefly show the *previous* target's cached health
status right after switching targets — `useSetTarget()` invalidates the
query but React Query keeps rendering the stale value until the refetch
lands. Confirmed live: Mattermost's Docker container turned out to be
genuinely running in the background (unrelated, from earlier in this
session), which is what made the stale-true flash visible. Fixed using
data already added in Phase 5 for exactly this: `/api/environment/health`
echoes back which target it actually checked, so both components now only
trust `target_up` when `envHealth.target === activeTarget.name`.

**Verified live, real subprocess, real HTTP, not mocked**: cold-started
from a genuinely down NaViQ server, triggered a real fresh reset through
the real running API — watched `manage.py runserver` actually spawn, the
real dev server respond (`"NaViQ dev server ready after 8.2s"`), a real
`GET /login/` return `200`, and `/api/environment/health` correctly flip.
**Re-ran the exact same reset a second time** while the server was already
up — confirmed idempotent (`"NaViQ dev server already running"`, no
double-spawn). **Drove the full jury-facing flow through a real headless
browser**: pick NaViQ in the TopBar picker → click Fresh reset → sampled
the Run button's disabled state roughly once a second across the entire
~45s reset window → never once enabled prematurely → correctly enabled
only once the reset genuinely completed. Zero terminal commands used at
any point in that flow. 195/195 tests green (7 new: `ensure_naviq_server_running()`'s
no-op/start/exit-failure/timeout paths and `stop_naviq_server()`'s
terminate/no-op/already-exited paths, `requests.get`/`subprocess.Popen`
mocked — a real server start is covered by the live verification above,
not the unit tests).

## Phase 6 — End-to-end validation

**Goal:** prove it, don't just believe it.

- [x] **Task 6.1 (done 2026-08-10)** — Ran for real. `main.py`'s B6
      blocks on a bare `input()` expecting a human to have hand-written
      `results/validated_payloads.json` — same Windows/Git-Bash stdin
      issue hit earlier this session, same fix (monkeypatch `input()`
      in-process). The patched function did real work, not a stub: read
      B5's actual output and auto-approved the first 3 non-empty
      candidates (1 payload each — real Groq-quota discipline, B3 alone
      had already been run live against NaViQ twice earlier today), same
      JSON shape `/api/validate` itself writes.

      **Real result, run id 14, `restore` mode, 71s total:**
      `ensure_naviq_server_running()`'s restore-mode safety net fired for
      real (server was down, started in 12.7s) — first live proof that
      exact code path actually works, not just its unit tests. B3: 119
      real `.py` files found, 10 scanned, 0 findings saved — every "not
      found" placeholder the LLM returned was correctly caught by today's
      filter (confirms that fix generalizes past the files it was built
      against). B4: real login, 14 real pages crawled. B5: 20 real
      payloads generated. B7: all 3 approved targets were on the contact
      form (email/name/message) — confirms `_fill_sibling_fields()` is
      working in the full real pipeline, not just the earlier isolated
      test: all 3 got genuine `302`s (not the pre-fix "Something went
      wrong" rejection), meaning the *other* two fields were correctly
      auto-filled each time. 0 anomalies (Django's auto-escaping, already
      established). B9: 0 correlated findings — correct given 0 static
      + 0 dynamic anomalies, nothing to correlate. Saved as Past Run id 14,
      visible in the frontend.
- [x] **Task 6.2 (done 2026-08-10)** — Full test suite: 195/195 green,
      confirmed both before and after the live runs. For the Mattermost
      run itself, Mattermost's Docker container turned out to hold real
      data unrelated to this session (running since 2026-08-08) — checked
      with the user before wiping it via `--mode fresh` rather than
      assuming; confirmed destructive reset was fine.

      **Real result, run id 15, `fresh` mode, ~2m16s total:** full
      teardown → bind-mount volume wipe → rebuild → boot (70.4s) →
      automated System Admin creation (no manual fallback needed) → seed
      → pipeline, exactly the sequence this mechanic has always run,
      unmodified by anything done this session. B3: 2057 real files found
      (Mattermost's actual size, vs. NaViQ's 119), 10 scanned, 6 findings
      saved — including a **genuine, real hardcoded secret**
      (`GiphySdkKey: 's0glxvzVg9azvPipKxcPLpXV0q1x1fVP'` in Mattermost's
      own `default_config.ts`) correctly *not* suppressed by today's A02
      prompt fix, alongside several correctly-suppressed "not found"
      placeholders on the same file — real, side-by-side proof that fix
      discriminates true positives from false ones rather than just
      suppressing the whole category. (Worth being precise, not
      oversold: a Giphy SDK key is typically a client-facing, low-sensitivity
      credential by design, not necessarily a severe finding on its own —
      what matters here is the detection was accurate, not that this
      specific key is a serious vulnerability.) B7: 2 of 3 approved
      targets executed (the third was `fileUploadInput`, already and
      correctly skipped — pre-existing behavior, not new), both
      `post_textbox` XSS payloads reflected in Mattermost's own JSON API
      response — **0 anomalies, which is the real, live, first-time proof
      that today's `XSS_reflected` false-positive fix works against
      actual live Mattermost**, not just replayed historical data. B9: 6
      correlated findings, all `POSSIBLE` (the static findings, none
      matched by a dynamic anomaly since B7 tested different code paths
      than what B3 flagged) — matches this task's own stated expectation
      exactly. Saved as Past Run id 15, confirmed side by side with the
      NaViQ run in Past Runs.

      Also noticed, not a new issue: B4 logged one non-fatal timeout
      warning crawling a thread-view page
      (`Page.wait_for_selector: Timeout 8000ms exceeded` on
      `.channel-header, #channelHeaderTitle`) — handled gracefully by
      B4's existing per-page error collection, didn't stop the crawl.

## `results/` per-target separation (done 2026-08-10, ahead of Phase 7)

Not one of the original numbered tasks — flagged by the user as the top
priority right after Phase 6 landed, once running the NaViQ run (Task 6.1)
then the Mattermost run (Task 6.2) back to back made it a live, visible UI
bug rather than a theoretical risk: `results/B7_dynamic_attacks.json`
(and every other block's output) is a single fixed filename regardless of
which target wrote it, so run 15 (Mattermost) silently overwrote run 14's
(NaViQ) output. Every block (B3 static, B4/`attack_surface`, B5 payloads, B6/
`validated_payloads`, B7 dynamic attacks, B8 dynamic, B9 correlation) wrote
to a fixed `results/{block}.json` path, and `api.py`'s `GET /api/results`/
`GET /api/results/{block_name}` read those same fixed paths directly — so
the live "Hybrid pipeline" tabs (not Past Runs, which was already correctly
isolated via SQLite) could show a completely different target's stale data
than whatever was currently selected in the TopBar picker.

Precedent already existed for the fix: B3's own file-list cache had
already gotten this treatment (`results/{target}_files_list.txt`, see "B3
target-awareness" above) after an identical collision. Generalized that
same convention to every block via one shared helper,
`result_path(target_name, filename)` in `blocks/targets.py`
(`results/{target}_{filename}`), and threaded a `target_profile` parameter
through every function that previously hardcoded a `results/...` path:
`main.py` (`save_result`, `run_static_analysis`, `run_dynamic_discovery`,
`execute_attacks`), `blocks/generate_payloads.py`, `blocks/human_review.py`,
`blocks/analyze_results.py`, `blocks/correlate_results.py`, and
`blocks/dynamic_injector.py`. All default to Mattermost when omitted (same
"zero behavior change for existing callers" convention used throughout this
plan), but every real call site in `main.py`'s `main()` and `api.py`'s
`run_pipeline_until_b6()`/`run_pipeline_from_b7()` now passes the actual
active target explicitly.

Went further than just the block JSONs once it was clear the same
collision applied to per-payload evidence: B7's screenshots/videos
(`results/dynamic/`, `results/videos/`) were keyed only by payload id
(e.g. `"1_1"`), which resets every run and isn't unique across targets —
two targets run back to back could silently overwrite each other's
screenshots too, corrupting a Past Run's image links even though the JSON
referencing them was itself safely snapshotted in SQLite. Fixed by scoping
both directories per target (`results/dynamic/{target}/`,
`results/videos/{target}/`) in `dynamic_injector.py`'s `_execute_one()`/
`run_payloads()` and `dynamic_analysis.py`'s `discover_attack_surface()`
(B4's own discovery video). No frontend change needed for this half — the
UI's `mediaUrl()` (`ui/src/lib/api.ts`) already strips a generic
`results/` prefix and forwards whatever's left to the `/media` mount, so a
deeper nested path works with zero changes there.

`api.py`'s `GET /api/results`/`GET /api/results/{block_name}` now glob/read
only `ACTIVE_TARGET`-scoped files, stripping the prefix back off so the
frontend still sees canonical keys (`"B3_static"`, not
`"naviq_B3_static"`) — no frontend contract change. `POST /api/validate`
and `POST /api/target`'s own file writes updated the same way.

`blocks/run_history.py`'s `finish_run()` needed a real fix, not just a
path swap: it used to `glob("*.json")` unconditionally, snapshotting
*every* JSON file in `results/` into whichever run just finished — meaning
once both targets' files started coexisting on disk (the entire point of
this fix), a NaViQ run's snapshot would also silently absorb Mattermost's
leftover files. Fixed by looking up the run's own `target` from the `runs`
table (already recorded by `start_run()`) and filtering the glob to that
target's prefix, stripping it back off before storing each row's
`block_name` — so `get_run()`/`list_runs()` consumers see the exact same
shape as before. A run predating the `target` column (`target IS NULL`,
e.g. this project's own orphaned row id 5) falls back to the old
glob-everything behavior, matching its original semantics exactly rather
than silently snapshotting nothing.

**Verified against real two-target runs, not fixtures**: cleared the local
`results/` folder (gitignored, disposable) of stale pre-fix files, then ran
`python main.py --target naviq --mode restore` followed by
`python main.py --target mattermost --mode restore` back to back — the
exact sequence that exposed the bug in Task 6.1/6.2. Real result: both
targets' full JSON output sets (`naviq_B3_static.json` through
`naviq_B9_correlation.json`, and the same eight files prefixed
`mattermost_`) coexisted afterward with no overwrite — `naviq_B7_dynamic_
attacks.json` still showed `total_executed: 15` and `mattermost_B7_
dynamic_attacks.json` showed `total_executed: 10`, matching each run's own
real execution count exactly. `results/dynamic/naviq/` and `results/dynamic/
mattermost/` (and the `videos/` equivalents) each held their own distinct
15/10 screenshots and videos with zero cross-target overwrite. Started
`api.py` live and hit the real endpoints: `GET /api/results` returned
NaViQ's `B7_dynamic_attacks.total_executed: 15` while NaViQ was active,
switched to Mattermost via `POST /api/target`, and the same endpoint
immediately returned `10` — the literal symptom the user reported, now
fixed and confirmed live. `GET /api/runs/17` (Mattermost) and
`GET /api/runs/16` (NaViQ) each returned canonical block names with the
correct target's own data, no leakage either direction. 197/197 tests
green throughout (2 new: one proving `run_history.finish_run()` doesn't
cross-contaminate when both targets' files coexist, one proving
`GET /api/results` only returns the active target's files).

## Past Runs target display (done 2026-08-10, ahead of Phase 7)

A small follow-up idea from the user once the separation fix above landed:
show which target each Past Run actually used, directly in the Past Runs
list, so the "which target produced this" question is answered by the UI
itself instead of requiring cross-referencing. Mostly already there on the
backend — `blocks/run_history.py`'s `list_runs()` already selected and
returned `target` per row, no backend change needed. The gap was entirely
frontend: `ui/src/lib/types.ts`'s `RunSummary` didn't declare a `target`
field at all (so it was silently dropped even though the API already sent
it), and `PastRunsView.tsx` never rendered it. Fixed by adding
`target: string | null` to `RunSummary` and a small badge in `RunRow`
next to each run's timestamp, using a local `TARGET_LABELS` map
(`mattermost` → "Mattermost", `naviq` → "NaViQ") rather than fetching
`GET /api/target`'s `available` list just for a label — a past run's own
target string is already exact, and this mirrors the same "closed set of
2 known profiles" design TopBar.tsx's picker already uses. Falls back to
the raw string for a run predating the `target` column.

**Verified live in the real running app, not just `tsc`**: started
`api.py` + the Vite dev server, drove a headless Chromium through the
landing page into the Past Runs tab, and confirmed every real historical
run (ids 1-17) shows the correct badge — alternating "Mattermost"/"NaViQ"
exactly matching each run's actual `target` column, including runs 14/16
(NaViQ) sitting right next to 15/17 (Mattermost) from the results-
separation verification above. `tsc --noEmit` clean; the one `eslint`
finding on `types.ts` is pre-existing formatting debt on an unrelated line
(`matched_static_finding`), not something this change introduced.

## Phase 7 — Docs

- [x] **Task 7.1 (done 2026-08-10)** — `readme.md` updated: a new dated
      paragraph in the intro changelog (2026-08-08 to 2026-08-10) plus
      dated bullets/Estado-line updates on B1, B3, B4, B7, and B13
      documenting the target-profile system, what's generic now (B1/B3/B4/
      B7 login+injection, the frontend picker) vs. still target-specific
      (concrete DOM selectors for anything beyond login), and NaViQ's
      status as the second validated target — including today's `results/`
      separation and Past Runs target-badge follow-ups. Section 8's
      roadmap point 1 ("soportar más de un sitio/target") marked
      superseded-in-part, same phrasing convention as `todo.md`'s own
      superseded entries. Test count updated 113 → 197 throughout. New
      closing paragraph added to "Resumen ejecutivo".
- [x] **Task 7.2 (done 2026-08-10)** — `fixes.txt`: added SESSION 8,
      covering the real bugs found across all of Phases 0-6 plus the two
      2026-08-10 follow-ups (the "#unknown" selector bug, hidden-field
      crowding in B5, the NaViQ honeypot, the XSS_reflected false
      positives, B3 never running against NaViQ, the A02 prompt fix + LLM
      placeholder bug, three NaViQ dev-server-automation bugs, the
      `results/` per-target collision, and the missing `target` field on
      `RunSummary`) — honest about what didn't generalize as cleanly as
      hoped (Phase 3's login/injection generalization was the highest-
      uncertainty phase, and its own real bugs are documented in section
      1 rather than glossed over). Explicitly scoped as the *condensed*
      technical record — full phase-by-phase detail stays in this file
      (`MULTI_TARGET_PLAN.md`), not duplicated there.
- [x] **Task 7.3** — `todo.md` §D: already done, alongside this plan's
      creation on 2026-08-08 (see its "superseded 2026-08-08" line) — kept
      in sync throughout every phase of this plan since, most recently
      with today's `results/` separation and Past Runs display entries in
      `todo.md` §E.

---

## Sequencing note

Phases 0→1→2→3→4 are a dependency chain (each needs the one before). Phase
5 (frontend) can start any time after Phase 1 lands, in parallel with 2/3 if
useful. Phase 6 needs everything before it done for real, not just believed
done. Budget the most uncertainty in Phase 0 (could reveal NaviQ's
authenticated area is harder than the public pages suggest) and Phase 3
(the response-capture generalization is genuinely novel work, not a port of
existing logic).
