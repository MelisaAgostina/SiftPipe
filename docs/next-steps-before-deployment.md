# Next Steps Before Deployment

Generated from [todo.md](todo.md), [AWS_HOSTING_TODO.md](AWS_HOSTING_TODO.md),
and [improvements.md](improvements.md) — the checklist items and review
findings scattered across those three files, pulled into one place with
exactly two phases: finish the remaining implementation work, then review the
finished result across the full software lifecycle.

---

## Phase 1 — Finish the code

Everything below is still open (unchecked) somewhere in `todo.md`,
`AWS_HOSTING_TODO.md`, or `improvements.md`'s "Where I'd invest next"
section. Grouped by area, not by source file.

Reorganized 2026-08-28 into execution order: resolve external/blocking
questions first, then finish code and feature work (architecture → business
logic → UI → i18n → security), then package it (Docker/Caddy/cloud-init),
then validate the packaged artifact (Live QA pass), then actually deploy —
so nothing gets rebuilt or re-validated twice along the way.

### Compliance / paperwork

*Do this first — it's a question for someone else, with response time you
don't control, and the answer may affect what deliverables need preparing.
Doesn't block anything else below.*

- [X] Ask your Profesor Coordinador: is a GitHub + Drive link acceptable
      instead of a physical CD/DVD for Anexo III point 3? Yes
- [X] Confirm with them: does the live AWS link (point 4) satisfy "software
      ejecutable" / "instructivo de instalación," or do they still want
      something separate? Yes, it's enough.
- [X] Prepare the accompanying deliverables regardless of the answer: source
      code link, DB/test-data export, informe files.

### Architecture

*Foundational fixes — do these first among the code work, since better
logging/config validation makes everything built afterward easier to debug.*

- [X] **Add Python lint/format/type-check config.** No `ruff`, `flake8`,
      `mypy`, or `pre-commit` today, and `requirements.txt` doesn't declare
      dev-tooling deps at all (not even `pytest`) — add config and declare
      the dev deps.
- [X] **Add a CI workflow.** No `.github/workflows` or equivalent exists —
      the test suite runs, but nothing triggers it automatically on
      push/PR. Do this early, right after the lint/type-check config above:
      everything else built in this phase from here on gets checked
      automatically, instead of only at the very end.
- [X] **Structured logging.** `main.py`'s `log()` uses `print()` with
      box-drawing characters — already caused one real `UnicodeEncodeError`
      on Windows cp1252. Swap to Python's `logging` module with levels, and
      write to a file (not just stdout) — matters once this runs headless on
      an EC2 box nobody is watching live.
- [X] **Fail-fast config validation.** A missing `ANTHROPIC_API_KEY` today
      only surfaces as a crash on the first LLM call, mid-pipeline. Add a
      startup check in `main.py`/`api.py` that validates required env vars
      before `/api/run` accepts a request.


### Logic, implementation & modularity

*From the 2026-08-26 full-lifecycle review — structural/duplication issues,
not new features. Grouped near Architecture since it's the same kind of
foundational cleanup, best done before the feature work below builds more on
top of the current structure.*

- [X] **Move B3's scan loop, LLM calls, and result-filtering into
      `blocks/static_scanner.py`.** That module currently only holds
      file-listing/prompt-building — the actual logic sits inline in
      `main.py`'s `run_static_analysis`. B4 through B9 each live entirely
      inside their own `blocks/*.py` module; B3 is the one exception.
- [X] **Extract a single shared LLM-call helper.** `ask_llm()`/`CLAUDE_MODEL`
      are defined twice, independently, in `main.py` and
      `blocks/generate_payloads.py` (same `client.messages.create(...)`
      shape, same JSON-code-fence stripping, same `temperature=0.0`);
      `blocks/analyze_results.py` repeats the strip-and-parse logic a third
      time as a defensive fallback. A model-version bump means remembering
      to update more than one place.
- [X] **Unify the two independently-maintained OWASP tables.**
      `blocks/static_scanner.py`'s `OWASP_SCOPE` (drives B3's prompt) and
      `blocks/taxonomy.py`'s `OWASP_TOP10_2025` (drives B9's correlation)
      aren't the same object — both files' own comments already acknowledge
      this ("keep this in sync with...") rather than one importing from the
      other. Only keep OWASP TOP10 2025, following MITREs standards.
- [X] **Derive `static_scanner.py`'s Mattermost scan-scope defaults from
      `targets.py`'s `MATTERMOST` profile** instead of hand-maintaining
      both. `DEFAULT_EXTENSIONS`/`DEFAULT_EXCLUDE_DIRS`/
      `DEFAULT_RELEVANT_DIRS` are meant to mirror the profile exactly — this
      is the pair recalibrated together for the directory-targeting fix, so
      it's two *correct* copies today, but still two copies.
- [X] **Reconsider `pipeline_results` as threaded-global mutable state.**
      Defined at module scope in `main.py`, mutated directly by every block
      function, shared into `api.py`'s two background `threading.Thread`s
      with no locking. Low real risk given the GIL and the
      `pipeline_state["running"]` guards, but it's unsynchronized shared
      state crossing a module boundary. Resolved by adding
      `api.pipeline_results_lock` (a `threading.Lock`), held by both
      background entry points (`run_pipeline_until_b6`,
      `run_pipeline_from_b7`) for their full run and by `/api/validate`'s
      `pipeline_results["B6"]` write — makes the no-concurrent-access
      invariant self-enforcing instead of dependent on the state-guard
      checks staying correct forever.
- [X] **Separate `main.py`'s orchestrator-script responsibilities from the
      definitions `api.py` actually needs to import.** `main.py` constructs
      the `Anthropic` client and calls `load_dotenv()` at import time, so
      importing `api.py` (which pulls `client`/`ask_llm`/block-runners
      straight from `main`) triggers all of that regardless of what `api.py`
      itself needs at that moment. Resolved by moving the client/logger/
      `pipeline_results`/`ask_llm`/block-entry-point definitions into new
      `blocks/pipeline.py`; `main.py` is now CLI-only (argparse + `main()`)
      and imports from `blocks/pipeline.py` on the same footing as `api.py`
      does, instead of being the thing `api.py` reaches into.
- [X] **Delete the dead code in `blocks/dynamic_analysis.py`**: its
      module-level `run_dynamic_discovery()` duplicates — without any of the
      target-scoping — what `main.py`'s own version (the one the real
      pipeline actually calls) does. Leftover from before target-awareness
      existed.
- [X] **Share B6's "filter approved indices, write
      `validated_payloads.json`" logic instead of implementing it twice.**
      `blocks/human_review.py`'s blocking console `input()` path and
      `api.py`'s `/api/validate` endpoint reimplement the same contract
      inline, sharing zero code despite a comment noting they're "the same
      contract." The `run_history` start/finish + try/except bookending, and
      the fresh-reset target-dispatch branching, are each also written out
      fully a second time in `api.py` rather than called once from a shared
      place.

### Business logic

- [X] **Route B5's relevance ranking through B9's taxonomy engine.** B5's
      `find_related_static_findings` is still pure keyword matching, while
      B9 already has a real CWE/OWASP taxonomy engine — the project's own
      docs already flag this inconsistency. Closing it is low-risk and
      already scoped: reuse what B9 has.
- [X] **Run-history trends/compare view.** "Compare this run vs. the
      previous run of the same target" (new vs. recurrent findings, severity
      delta) — `run_history.py` already has everything needed; mostly a new
      query + a UI panel, not new pipeline logic. Parked twice already in
      readme.md as "out of scope for now, possible future extension."
      Scoped down to the backend query only this round (per the doc's own
      split: the UI section below has its own "Trend/compare view in Past
      Runs" line item) — `blocks/run_history.py`'s `compare_with_previous()`
      plus `GET /api/runs/{run_id}/compare`. The UI panel remains open under
      the UI section.

### Efficiency

*Decision (2026-08-28): keep `MAX_FILES` at 10, or raise it to at most 15 —
not dynamic. Scanning more files means more real Anthropic API spend, so the
cap stays a deliberate cost control, not something to "fix." That changes
the priority of the first item below.*

- [ ] **B3's per-file LLM calls are fully sequential** — no concurrency or
      batching. Originally worth fixing mainly once `MAX_FILES` gets relaxed
      to something larger — since that's not happening (see decision above),
      this is now a nice-to-have for a modest speedup on today's small cap,
      not a blocker.

      **Decision (2026-09-01): deferred, not implemented.** Weighed
      deliberately rather than skipped by default:

      - *What it would buy:* parallelizing the up-to-10 per-file `ask_llm()`
        calls turns B3's own wall-clock time from "sum of every call" into
        roughly "the slowest single call" — real, but bounded by the
        `MAX_FILES` cap above, and it doesn't touch B4/B5/B7 (browser
        automation), which dominate a full pipeline run's total time anyway.
      - *What it would cost, in engineering risk:* unlike the other three
        items below (pure algorithmic fixes — same output, less repeated
        work, no new failure mode possible), concurrency is a different
        *kind* of change. It requires collecting each file's findings
        without letting two threads write into the shared results list at
        the same instant, and it's the sort of bug that a test suite often
        can't catch reliably — a race can pass 99 runs and fail the 100th.
      - *What it would cost against Anthropic's rate limits specifically:*
        Anthropic enforces three independent per-account ceilings —
        requests per minute, **input tokens per minute (ITPM)**, and
        **output tokens per minute (OTPM)** — scaled to the account's usage
        tier (see the account's own Limits page at
        [console.anthropic.com](https://console.anthropic.com) for the
        actual numbers; not something this codebase has visibility into).
        Sequential calls are naturally rate-limit-safe: each file's request
        waits for the previous one's full round trip before the next is
        sent, so the 10 calls in a B3 run are spread across however long
        those round trips take, never bursting. Running them concurrently
        doesn't change the *total* tokens spent — same 10 calls, same
        dollar cost either way — but it does compress that same spend into
        a much narrower time window, which is exactly what a *per-minute*
        limit is designed to catch. A small developer/thesis-scale account
        (not a scaled production key) is the case most likely to sit on a
        lower usage tier, i.e. the case where this risk is least
        theoretical.
      - *Net:* a modest, bounded time saving, purchased with a genuinely new
        failure mode (races) and a real chance of trading "always safely
        under the rate limit" for "sometimes hits it," for a code path that
        only matters during local iteration, not the one-shot jury demo run.
        Not worth it at this project's scale — revisit only if `MAX_FILES`
        is ever raised enough to make B3's own wall-clock time an actual
        bottleneck, not just a nice-to-have.
- [X] **Remove the flat `time.sleep(15)` that runs after every B3 run**,
      unconditionally — regardless of whether a re-run is actually imminent
      or anything was even found. Cheap, independent fix, unrelated to the
      file-cap decision.
- [X] **B9's `find_match` recomputes `infer_taxonomy()` on every inner-loop
      pass** instead of once up front — O(dynamic findings × static
      findings) overall. Trivial at today's scale (a small `MAX_FILES` keeps
      the static-findings side small too), but a one-line fix: compute
      `[(b3, infer_taxonomy(b3)) for b3 in b3_findings]` once, outside the
      loop.
- [X] **B7 re-scans the same response body multiple times** — separate
      `any(k in body for k in ...)` passes for SQLi markers,
      command-injection markers, and misconfiguration markers. Combine into
      one pass over the same lowercased string. Independent of the file-cap
      decision.

### UI

*Fast local iteration, no Docker needed yet.*

- [X] Trend/compare view in Past Runs (pairs with the business-logic item
      above). `PastRunsView.tsx`'s `ComparePanel` consumes
      `GET /api/runs/{id}/compare` via a new `useRunComparison()` hook —
      severity-delta badges (CRITICAL/HIGH/MEDIUM/LOW, colored by whether
      this run got worse or better) plus NEW/RECURRING/RESOLVED `Section`s
      reusing the existing `mapB9Entry` pipeline. Live-verified against real
      historical data (run #21 vs. #19, no pipeline run triggered, no API
      cost) in the actual browser via chrome-devtools.
- [X] **A visible failure surface for background pipeline errors.** New
      `useErrorToast()` hook (`ui/src/hooks/use-error-toast.ts`) fires a
      `sonner` toast the instant `status.error` / `environment-status.error`
      transitions from empty to a new value, wired into `SecPipelineApp.tsx`
      alongside the existing (now-supplementary) static sidebar text. TDD'd:
      5 unit tests cover the edge-detection state machine (first appearance,
      no re-fire on repeated polls, re-fire on a changed or recurring error).
- [X] A minimal empty-state/first-run guide ("pick a target → Fresh reset →
      Run") — a jury will be clicking around cold, unlike the developer. New
      `FirstRunGuide.tsx`, shown instead of the old generic "no active run"
      message when `usePastRuns()` returns zero runs (true first-time
      state); falls back to the original message once any run exists, so a
      returning user isn't shown the beginner walkthrough every time. 3
      render tests + a live check of the fallback path in-browser.
- [X] Driver.js-style guided tour across all utilities — built last so it
      could describe the compare view above. Added `driver.js` (approved
      new dependency) plus `data-tour` anchors across `TopBar`, `Sidebar`,
      and `Tabs`; `tour.ts` holds the 9-step script, `buildDriveSteps.ts`
      wires each tab-scoped step to switch tabs via `setTab` right before
      driver.js highlights it (TDD'd, 3 unit tests). Live-verified in the
      browser end to end, including the actual tab switch to "Review (B6)"
      rendering real payload-review content behind the tour popover.
- [~] **Add frontend test coverage.** Framework now installed and wired —
      `vitest` + `@testing-library/react` (+ `jest-dom`, `user-event`,
      `jsdom`), a standalone `vitest.config.ts` (kept separate from the
      app's `vite.config.ts`, which is wrapped by
      `@lovable.dev/vite-tanstack-config`'s TanStack Start/Cloudflare
      plugins — irrelevant to component tests and safer not to fight), and
      `npm test` running clean. 11 tests exist today, but all were written
      as TDD for *new* logic added elsewhere in this pass (the error-toast
      hook, the tour's tab-switching, `FirstRunGuide`'s branch) — writing
      *backfill* coverage for the existing content-heavy views
      (`Sidebar`, `PastRunsView`, etc.) is deliberately still deferred until
      after Internationalization, per this item's own note: those tests
      would assert on hardcoded English strings that i18n is about to move
      into a dictionary, so writing them now means rewriting them almost
      immediately after.

### Internationalization (en/es toggle)

- [X] **Frontend language toggle**, matching a pattern already proven
      elsewhere in this project: B10's PDF report
      (`blocks/report.py`) is already bilingual via plain string
      dictionaries (`REPORT_STRINGS`, `CWE_ES`/`OWASP_ES`), no library
      involved — the frontend can follow the same approach rather than
      reaching for something heavier. No i18n library is installed in
      `ui/package.json` today (checked 2026-08-28), so this is greenfield on
      the frontend side.
- [X] **Decision (2026-09-02): hand-rolled dictionary, not `react-i18next`
      — settled, not conditional.** Add `en.ts`/`es.ts` dictionaries plus a
      small `useLang()` hook backed by `localStorage` (so the choice
      persists across reloads without a backend round-trip), also checking
      `navigator.language` on first load before `localStorage` has
      anything — decided 2026-09-02, needed specifically because the login
      page (Security, sequenced right after this item) sits in front of
      the app shell and can't reach the `TopBar.tsx` toggle otherwise.
      - *Why not `react-i18next`, concretely:* a real scan of
        `ui/src/components/secpipeline/` put the genuinely user-facing
        string count in the low hundreds — well under where a library's
        namespace-splitting/lazy-loading starts paying for itself (roughly
        several hundred strings or 3+ languages). Values needing
        interpolation (`Run #{id}`, `{confirmed}/{total} confirmed`) are
        just template-literal functions in the dict, the same shape
        `blocks/report.py`'s `REPORT_STRINGS` already uses — not a gap
        `react-i18next` closes that a plain object can't. A `strings.ts`
        object declared `as const` also gets autocomplete and
        typo-catching for free from TypeScript; `react-i18next` needs an
        extra type-augmentation step for the same guarantee. And it's zero
        new dependencies, consistent with every other choice in this repo.
      - *Precedent:* OWASP ZAP and SonarQube — arguably the two most
        internationalized tools in this exact space — both translate via
        plain resource-bundle files decoupled from core logic, falling
        back to English wherever nothing's translated yet. Same shape of
        solution, not a shortcut.
      - *Revisit only if* a third language gets added, real plural rules
        become necessary (not the existing `payload(s)` hack), or the
        string count grows an order of magnitude past today's scan.
- [X] Toggle placement: `TopBar.tsx`, next to the existing target picker —
      same closed-set-of-two-buttons pattern already used there, not a
      dropdown/free-text control.
- [X] **The actual work is mechanical, not architectural**: externalize every
      hardcoded string across `ui/src/components/secpipeline/` (`Sidebar`,
      `TopBar`, the pipeline-stage views, `FindingRow`, `PastRunsView`,
      `LogsView`, `PayloadReviewView`) into the dictionary. Sized as a few
      hours of mechanical work, not a multi-day effort — no backend changes
      needed, this is frontend-only (the PDF report's own bilingual support
      is separate and already done).

      **Done 2026-09-03.** `ui/src/lib/strings.ts` (the shared `Strings`
      type), `ui/src/lib/en.ts`/`es.ts` (the two dictionaries), and
      `ui/src/hooks/use-lang.ts` (`useLang()`, a `useSyncExternalStore`-backed
      hook so every component re-renders together on toggle, no Context
      provider needed). Scope ended up wider than the 7 named files once
      actually tracing what renders inside them — done with sign-off, not
      silently: `QueryState.tsx` ("Loading...", error-prefix text — shared by
      all 7 views), `data.ts` (phase/tab/prerequisite labels, restructured to
      carry only stable `id`s with the label text moved into the
      dictionaries), `Tabs.tsx`, `FirstRunGuide.tsx`, `SecPipelineApp.tsx`
      ("Guided tour", toast titles), and `mappers.ts` (the static labels
      mixed into `UIFinding` — "FORM"/"INPUT"/"ERROR LLM", not the AI content
      alongside them). `tour.ts`'s `TOUR_STEPS` constant became
      `buildTourSteps(t)` so the guided tour renders in whichever language is
      active; `TourStep`'s own shape (and `buildDriveSteps.ts` plus its 3
      tests) stayed untouched.

      Two categories of string were deliberately left English-only beyond the
      AI-content boundary below: backend enum/status values shown verbatim
      (B8's `result`, B9's `classification`, `severity`, B3's `confidence`) —
      treated the same as the AI-generated text they classify, not chrome —
      and the "English"/"Español" labels on the *report-language* picker in
      the Past Runs download menu, which name the report's own language
      choice rather than describe UI chrome. `RunSummary.status`
      (running/completed/error) is different — pipeline lifecycle state, not
      AI output — and is translated.
- [X] Do this after the empty-state/first-run guide and Driver.js tour
      above, so new UI text only needs to be externalized once instead of
      twice.
- [X] **Scope boundary: AI-generated finding text (vulnerability names,
      evidence, rationale from B3/B5/B8/B9) stays English-only, regardless
      of the toggle.** Raised as a real design question, not silently
      assumed, so the decision is recorded here rather than left implicit.

      **Decision (2026-09-02): keep the toggle scoped to UI chrome only.**
      Weighed one real alternative, not skipped by default:

      - *The alternative considered:* let the user pick an "analysis
        language" at run-start — a separate control from the
        always-instant chrome toggle, since it can only take effect the
        moment a run starts — thread it into B3/B5/B8's prompts so
        findings come back in that language, and show a clear inline
        warning next to the Run button ("findings will be generated in
        &lt;language&gt;") so there's no silent mismatch between what the
        toggle promises and what a run actually produces. Would also get
        its own Driver.js tour step.
      - *Why it's not the default choice:* English is the standard working
        language of the software/security industry — CWE/CVE entries,
        OWASP documentation, CVSS descriptions, and the vast majority of
        the source code, commit messages, and library documentation this
        pipeline analyzes are already in English. Findings that quote
        source code verbatim (the `evidence` fields) stay English/code
        regardless of analysis language, so translating only the prose
        around them buys partial, inconsistent bilingualism at real
        engineering cost.
      - *What it would cost if built anyway:* real backend work across
        multiple prompts (B3/B5/B8), not the "frontend-only, a few hours"
        scope the rest of this section has; a second, run-time-only
        control distinct from the chrome toggle; and an explicit
        commitment to surfacing the mismatch (a run's findings staying in
        whatever language was active when it started, not the language
        you're currently browsing in) rather than hiding it.
      - *Precedent:* neither OWASP ZAP nor SonarQube — arguably the two
        most internationalized tools in this space — translate freshly
        generated finding text; both only translate a closed, pre-written
        vocabulary (their own rule/alert catalog), which is exactly what
        `CWE_ES`/`OWASP_ES` already do here. Neither has an LLM writing
        new prose per scan the way B3/B5/B8/B9 do, so there's no
        established pattern to follow either way for that specific piece.
      - *Net:* keep AI-generated finding text English-only, matching both
        the PDF report's existing precedent and the industry's own default
        working language. Revisit only if a specific audience need (e.g. a
        non-English-fluent stakeholder reviewing findings directly, rather
        than just the UI chrome around them) makes this a real requirement
        rather than a nice-to-have.

      **Verified 2026-09-03**, live in the browser against real historical
      run data (#21, no pipeline run triggered, no API cost): toggling ES
      translated every chrome string (headings, tabs, buttons, empty/error
      states, section titles with real interpolated counts, the guided tour)
      while `mattermost-src/...` vulnerability titles, CWE/evidence text,
      rationale, and the CONFIRMED/POSSIBLE/DISCARDED/HIGH/MEDIUM labels
      stayed in English throughout — confirms the mapper-level boundary
      actually holds at runtime, not just by code inspection.

### Security (before the AWS jury deployment specifically)

*Finish the real auth model before packaging the app below — so the Docker
image ships with the real security posture already in it, and the Live QA
pass further down exercises it directly instead of a stand-in.*

- [X] **Real session-cookie login gate**, replacing the current
      API-key-in-the-JS-bundle pattern: Starlette's `SessionMiddleware`
      (already ships with FastAPI), a `POST /api/login` checking a shared
      passphrase against `SIFTPIPE_ADMIN_PASSWORD` and setting
      `request.session["authenticated"] = True`, and a dependency applied
      globally to every route. Fixes the unauthenticated-GET-endpoint gap
      identified in Phase 2's security review *by construction* (every route
      gated, not just the mutating ones), and the secret never touches
      client-side JS — the browser only holds an opaque httpOnly cookie.
      Deliberately one shared passphrase, not full accounts/JWT/roles — the
      right scope for a single-audience-tier demo box with a defined
      teardown date, but still defensible if a committee member asks how the
      deployment was secured (relevant given the thesis's own subject is
      OWASP vulnerability detection, A07 included).

      **Design notes (2026-09-02) — nothing built yet, audit + rationale
      only:**

      - *Current state, audited against `api.py` directly:* the only auth
        that exists today is `require_api_key()` — a no-op unless
        `SIFTPIPE_API_KEY` is set at deploy time, and even then it only
        gates 5 POST routes (`/api/target`, `/api/environment/reset`,
        `/api/run`, `/api/validate`, `/api/reset`). Every `GET` route —
        results, past runs, PDF reports, logs, status — has zero
        protection today, key or no key, since none of them carry the
        `Depends(require_api_key)` dependency. No `SessionMiddleware`,
        `/api/login` route, or `SIFTPIPE_ADMIN_PASSWORD` handling exists
        anywhere in the repo yet — this item is 0% built, design-only.
        The existing key is also a weak stopgap even where it does apply:
        it's baked into the frontend's JS bundle (`VITE_API_KEY`), so
        anyone who opens devtools can read it back out — enough to keep a
        stray bot off an unlisted demo link, not real access control.
      - *Why this design needs no database:* a single shared passphrase
        means there's no per-user account to store, so there's nothing to
        look up on any request. The flow is stateless on the server:
        `POST /api/login` compares the submitted password against
        `SIFTPIPE_ADMIN_PASSWORD` once, and on success `SessionMiddleware`
        encodes `{"authenticated": true}` into a cookie it
        cryptographically *signs* (not encrypts) with a separate secret
        key. The browser presents that cookie on every later request, and
        the server only ever re-checks the signature — no session table,
        no per-visitor row, nothing persisted server-side. This only works
        *because* the scope is one shared passphrase and not per-user
        accounts; real accounts would need somewhere to store each user's
        credentials, which is exactly what this design avoids.
      - *Two secrets this needs at deploy time, both env vars, neither
        hardcoded:* `SIFTPIPE_ADMIN_PASSWORD` (the passphrase itself) and a
        session-signing secret key (passed to `SessionMiddleware`'s
        `secret_key=`). The signing key matters more to get right —
        whoever holds it could forge their own valid
        `{"authenticated": true}` cookie without ever knowing the
        password, so it needs to be a real generated secret set at deploy
        time, never a default or placeholder left in source.

      **Sequencing addendum (2026-09-02): build this after Internationalization,
      not before.** Two reasons, not just "keep the plan tidy":
      - *Avoids a retrofit.* The login page is new UI with its own hardcoded
        copy. Built before the i18n dictionary exists, that copy has to be
        found and migrated back into it later; built after, it's authored
        natively against `useLang()` from the start — written once, not
        written then rewritten.
      - *The login page needs the browser-language default specifically.*
        It sits in front of the app shell, so `TopBar.tsx`'s language
        toggle isn't reachable from it yet — `useLang()` checking
        `navigator.language` on first load (agreed on 2026-09-02, not yet
        built) is the *only* way a Spanish-speaking visitor's first screen
        shows in Spanish at all. Skipping ahead to Security first would
        ship a login page that can't do this.
      This matches the doc's own top-of-file execution order (`architecture
      → business logic → UI → i18n → security`), so it isn't a new
      constraint — just made explicit here since it came up directly while
      scoping this item.

      **AWS-compatibility check (2026-09-02), against a real reference
      implementation reviewed but not merged:** a full FastAPI/TanStack
      Router version of this design was drafted and reviewed (constant-time
      password check via `hmac.compare_digest`, signed HMAC-SHA256 session
      token, `GET /api/session` for the frontend route guard, in-memory
      rate limiting) — sound on its own terms, but checked against
      `AWS_HOSTING_TODO.md`'s actual plan (frontend → Cloudflare Pages,
      backend → a separate AWS EC2 host) turned up real, not hypothetical,
      gaps to fix before wiring it in for real:
      - *Cross-domain cookie, the one that actually breaks it.* Cloudflare
        Pages and the EC2 host are different registrable domains, not
        subdomains of one domain (unlike `localhost:5173` ↔
        `localhost:8000` today, which are "same site" despite the
        different ports). A `SameSite=Lax` cookie — what both drafts used
        — is silently **not sent** cross-domain: login would return 200,
        but the cookie would never actually arrive on the next request.
        Needs `SameSite=None` + `Secure=True` in the deployed environment
        specifically (HTTPS-only, and both attributes required together),
        while staying `Lax` for local dev — an environment-conditional
        setting, not a hardcoded one.
      - *The reverse proxy breaks IP-based rate limiting unless configured
        for it.* The AWS plan puts nginx in front of `api.py`. Without
        forwarding + trusting the real client IP, the login rate limiter's
        `request.client.host` sees nginx's address for every visitor, not
        each visitor's own — collapsing the whole rate limit into one
        shared bucket. Needs a trusted `X-Forwarded-For` read once nginx
        (or Caddy, if that swap happens) is actually in front of it.
      - *Same open secrets-handling gap as Architecture's Secrets Manager
        item, not a new one.* `SIFTPIPE_ADMIN_PASSWORD` and the session
        secret land in the EC2 box's hand-edited `.env` under the current
        plan, same as `ANTHROPIC_API_KEY` today — consistent with that
        item staying deferred, just worth knowing these two inherit it too
        rather than being a separately-decided exception.

      **Built 2026-09-03, TDD throughout (backend: `tests/test_auth.py` +
      `tests/test_api_auth.py` via `fastapi.testclient.TestClient`, real
      HTTP requests through the actual middleware stack, not direct handler
      calls — the whole point is that `SessionMiddleware` put
      `request.session` there; frontend:
      `LoginPage.test.tsx`, 5 RTL tests against each HTTP status branch).
      `blocks/auth.py` is the new pure-logic layer — `verify_password()`
      (hashes both sides to a fixed-length digest before
      `hmac.compare_digest`, so a wrong-*length* guess can't leak timing
      either, not just a wrong-content one), the in-memory rate limiter, and
      its own `validate_required_env_vars()` mirroring
      `blocks/pipeline.py`'s pattern for `ANTHROPIC_API_KEY`. `api.py` gained
      real `SessionMiddleware` (not a hand-rolled token — considered a
      reviewed reference implementation that used its own HMAC-SHA256
      signing instead, went with Starlette's own library code, less custom
      crypto for a committee to have to trust), `POST /api/login`/
      `GET /api/session`/`POST /api/logout`, and an `APIRouter(
      dependencies=[Depends(require_session)])` covering all 16 previously
      open-or-key-gated routes — `require_api_key()`/`SIFTPIPE_API_KEY`
      retired entirely rather than stacked alongside the new gate. Both
      AWS-compatibility fixes above are live, not just designed:
      `SameSite`/`Secure` and the trusted-`X-Forwarded-For` IP both key off
      `FRONTEND_ORIGIN` being set (the same "are we actually deployed"
      signal already used for CORS), and `CORSMiddleware` gained
      `allow_credentials=True` (was missing — without it the browser
      silently refuses to send/receive the cookie cross-origin at all).
      `SIFTPIPE_ADMIN_PASSWORD` is *always* required now (not a no-op like
      the old key when unset) — your own call, traded local-dev convenience
      for the local rehearsal actually matching the deployed flow. New
      runtime dep: `itsdangerous` (`SessionMiddleware`'s own signing
      requirement). Frontend: `LoginPage`/`login.tsx` adapted from a
      reviewed zip (its `beforeLoad`/`redirect` route-guard idiom on
      `/app` reused close to as-is; its own `VITE_API_URL` swapped for the
      existing `VITE_API_BASE`; every hardcoded string moved into
      `useLang()`, since this is new UI built after the i18n dictionary
      exists); `lib/api.ts` switched from the `X-API-Key` header to
      `credentials: "include"` on every request. Verified live in the
      browser: `/app` → `/login` redirect, wrong-password error message,
      both in Spanish (localStorage-persisted language, read correctly
      before the app shell is even reachable — the exact scenario this
      sequencing decision was made for).

      **Known gap, not yet decided:** `/media` and `/evidence`
      (`app.mount(...)` StaticFiles, serving B7 screenshots/videos) aren't
      covered by `require_session` — FastAPI dependencies attach to router
      *routes*, not to `app.mount()`. A URL only becomes visible by being
      referenced somewhere behind the login gate, so this isn't wide open,
      but it means someone with a direct evidence URL (shared out of band,
      or brute-forced) could view it without logging in. Not fixed here
      since gating a static mount needs a different mechanism than
      `Depends()` (a custom authenticated file-serving route, most likely)
      — flagged for a decision rather than silently left as a surprise.

- [X] **CSRF protection, and the auth-flow bugs live-testing it turned up
      (2026-09-04).** The `X-Requested-With` header check from the prior
      session had unit tests but no real-browser confirmation; tested
      directly against the running app this round — request carrying the
      header returns `200`, request without it returns `403`. Confirmed
      correct, not just test-green.
      - *Real, separate bug found and fixed: post-login redirect was
        completely broken.* This UI is TanStack Start, SSR by default.
        `LoginPage.tsx` redirected via `window.location.href` — a hard
        navigation — which meant `/app`'s `beforeLoad` session check ran on
        the *server* on the next page load, and Node's `fetch()` there has
        no access to the browser's cookie jar. Every login was succeeding
        and then silently bouncing back to `/login` anyway. Fixed by
        switching to the router's client-side `navigate()` instead:
        `LoginPage.tsx` now takes an `onAuthenticated` callback, and
        `login.tsx` supplies it. TDD'd, then live-verified in the browser.
      - *Landing page now reflects auth state* instead of relying on
        `/app`'s guard to silently redirect. New `useSessionAuthenticated()`
        hook: "Open the pipeline" goes to `/app` when already logged in,
        "Log in" goes to `/login` otherwise.
      - *Logout implemented.* The backend endpoint already existed
        (`POST /api/logout`, from the session-gate work above) but nothing
        in the UI called it. Added an icon button in `TopBar.tsx`, a
        `useLogoutHandler()` hook, and a confirmation toast — required
        moving `<Toaster/>` to the root layout so it survives the
        navigation away from the app shell.
      - *Mid-session-expiry page* built from a reviewed mockup (picked
        "Plate 403" over two other variants). Wired to fire only when a
        session dies *mid-use* — a visitor who was never logged in still
        gets the plain silent redirect, not this page. Live testing caught
        a real race (a stale in-flight request could resolve after
        re-login and falsely re-trigger the expiry page) — fixed and
        stress-tested.
      - Repo cleanup alongside this work: removed `.playwright-mcp/`,
        `.ruff_cache/`, and stray screenshots; added `.playwright-mcp/` to
        `.gitignore`.

### The highest-leverage item

*Code and feature work above should be stable before this — containerizing
mid-feature-churn just means rebuilding the image repeatedly for no reason.*

- [ ] **Containerize SiftPipe itself.** No Dockerfile exists for the project
      today — only Mattermost's own submodule Dockerfiles. A Dockerfile for
      `api.py` (Python + Playwright/Chromium deps baked in) plus a
      `docker-compose.yml` that also brings up Mattermost turns AWS setup
      into "install Docker, `docker compose up`" instead of the current
      multi-step manual sequence (venv, `playwright install --with-deps`,
      nginx, certbot, systemd unit, `git pull` + reinstall on every update).
      Pays off twice: easier AWS deploy *and* reads as a more deployable
      product for the Informe final, not a script that only ran on one
      machine.

### AWS deployment ease

- [ ] Docker (see "highest-leverage item" above).
- [ ] **Caddy instead of nginx + certbot** — automatic HTTPS with a ~5-line
      Caddyfile, meaningfully less manual TLS setup for a short-lived demo
      box.
- [ ] A cloud-init/user-data script (or a minimal Terraform file) so EC2
      provisioning is one launch instead of a manual checklist —
      reproducibility matters more here since the plan is spin-up → demo →
      tear down, not maintain forever.

### Testing / QA

*Do this against the containerized build above, not the bare-venv setup —
otherwise you're validating a deployment path you're about to replace.*

- [ ] **Add at least one real end-to-end smoke test.** Everything today is
      unit-level, against fakes and mocks — nothing spins up the app and
      runs it end-to-end as part of the test suite. Wire it into the CI
      workflow from the Architecture section so it's not a one-off; build it
      before the manual pass below so an automated net exists first.
- [ ] **Live QA pass** — not yet run. Actually start Mattermost/`api.py`/the
      UI dev server and click through real flows (target picker, Fresh
      Reset, Past Runs against the existing `siftpipe_history.db`,
      empty/error states) rather than reading code.

### AWS deployment steps (infra, not code — from `AWS_HOSTING_TODO.md` §2)

*Only once the containerized build has passed the QA pass above — this is
real time and (small) money, so validate locally first.*

- [ ] **Secrets via AWS Secrets Manager/SSM** instead of a hand-edited
      `.env` on the box.

- [ ] `playwright install --with-deps chromium` on the server.
- [ ] `git submodule update --init --depth 1` after cloning on the server.
- [ ] Set an AWS Budget alert ($10 / $25 / $50).
- [ ] Launch EC2 (t3.medium, Ubuntu 24.04, security group closed except
      80/443) + allocate an Elastic IP.
- [ ] One-time server setup: Docker, Python, nginx, certbot, clone +
      submodule, venv + deps, `.env` files.
- [ ] TLS: pick a domain or use the free AWS hostname, run certbot, confirm
      nginx proxies to the API.
- [ ] `systemd` unit for the API; confirm Mattermost's `unless-stopped`
      restart policy.
- [ ] Deploy frontend to Cloudflare Pages with `VITE_API_BASE` set.
- [ ] Go-live check: `/api/health`, one full B3→B9 dry run, then send the
      link.
- [ ] Afterward: stop or terminate everything.

### Optional / supplementary (not required by the thesis's formal objectives)

*Lowest priority — only if time remains after everything above.*

- [ ] A third pipeline target (`lutto_website` is lower-effort and
      higher-certainty; `TC_Grupo9` is harder but a valid "held up under
      scrutiny" result either way) — see `improvements.md`'s "Scoping a
      third target" section for the full comparison. The actual pick is
      still open.
