# SiftPipe

An LLM-driven pipeline for automated web application security assessment — static source analysis, dynamic attack-surface discovery via Playwright, LLM-generated payloads, real browser-based attack execution, and static/dynamic correlation, all exposed through a FastAPI backend and a React frontend. Built as a bachelor's thesis on automated OWASP vulnerability detection.

---

## Pipeline Blocks

| Block | Purpose | Status |
|---|---|---|
| `B1` | Environment prep — Docker fresh reset (Mattermost) or dev-server bring-up (NaViQ), per-target seeding | Done |
| `B3` | Static analysis — LLM-based source review per target, OWASP/CWE tagging | Partial |
| `B4` | Dynamic discovery — Playwright same-origin BFS crawl, form/input extraction | Partial |
| `B5` | Payload generation — LLM-generated attack payloads from B3 + B4 output | Partial |
| `B6` | Human review — validates/filters B5 payloads before B7 runs them | Done |
| `B7` | Attack execution — runs validated payloads against real forms, captures responses/screenshots/video | Implemented, tested |
| `B8` | Results analysis — LLM classifies each B7 attempt as confirmed/possible/discarded | Implemented, tested |
| `B9` | Correlation — matches dynamic findings back to static ones (CWE-exact → LLM judge → OWASP → text fallback), scores severity | Partial |
| `B10` | Reporting — bilingual PDF export per run, grouped remediation by CWE | Partial |
| `B13` | UI — React dashboard for the full pipeline, human review, and past-run history | Partial |
| `B0`, `B2`, `B11`, `B12` | Orchestration, scope definition, triage integration, extended persistence | Not started |

Full block-by-block detail (what's implemented, what's a heuristic vs. a real fix, every bug found and how) lives in [docs/readme-old.md](docs/readme-old.md).

---

## Stack

- **Backend:** Python, FastAPI, Anthropic Claude (`claude-haiku-4-5`), Playwright, SQLite (run history)
- **Frontend:** React 19, TanStack Start/Router, TypeScript, Tailwind, Radix UI
- **Testing:** 360+ backend tests (`unittest`), 178+ frontend tests (Vitest)
- **CI/Security:** GitHub Actions, CodeQL, Dependabot, secret scanning + push protection

---

## Project Structure

```
SiftPipe/
├── main.py                     # Console entrypoint — runs the pipeline B1→B9 by target/mode
├── api.py                      # FastAPI app — every block exposed as an endpoint, session-cookie auth
├── seed.py                     # Seeds a fresh Mattermost instance with test data
│
├── blocks/                     # Pipeline logic — see detail below
│
├── ui/                         # React/TanStack Start frontend
│   └── src/
│       ├── components/
│       │   ├── secpipeline/    # Pipeline views: Sidebar, CorrelationView, PastRunsView, etc.
│       │   ├── auth/           # Login page, session guard
│       │   └── ui/             # Shared UI primitives (shadcn/Radix-based)
│       ├── lib/                # API client, React Query hooks
│       └── routes/             # TanStack Router routes
│
├── tests/                      # Backend test suite, one file per block/module
│
├── mattermost/                 # Docker Compose stack for the Mattermost target
├── mattermost-src/             # Mattermost source (git submodule, scanned by B3)
│
├── results/                    # Per-run pipeline output (gitignored)
├── evidence/                   # B7 screenshots/videos (gitignored)
├── siftpipe_history.db         # SQLite run history
│
└── docs/                       # Project documentation — see below
```

---

## blocks/ — Detail

```
blocks/
├── pipeline.py           # Shared primitives: Anthropic client, ask_llm(), run_static_analysis(),
│                          #   run_dynamic_discovery(), execute_attacks(), startup env-var validation
├── llm.py                # Shared Anthropic call shape (JSON verdict, fence-stripping) used by every
│                          #   LLM-calling block
├── targets.py             # TargetProfile — single source of truth per target (selectors,
│                          #   credentials, B3 scan config)
├── environment.py         # B1 — fresh_reset() (Mattermost/Docker) and naviq_fresh_reset() +
│                          #   dev-server lifecycle (NaViQ)
├── static_scanner.py      # B3 — file listing, extension/dir filtering, prompt construction
├── crawler.py             # B4 — generic same-origin BFS crawl for attack-surface discovery
├── dynamic_analysis.py    # B4 — orchestrates login, crawl, form/input extraction
├── mattermost_auth.py     # Shared login-selector resolution (with fallback), used by B4 and B7
├── generate_payloads.py   # B5 — LLM-generated payloads from B3 + B4 output
├── human_review.py        # B6 — console-mode payload validation (API-mode lives in api.py)
├── dynamic_injector.py    # B7 — executes validated payloads, detects anomalies, captures evidence
├── analyze_results.py     # B8 — LLM classification of each B7 attempt
├── correlate_results.py   # B9 — static/dynamic correlation engine (CWE match → LLM judge → OWASP
│                          #   → text fallback), reuses judgments across runs
├── scoring.py             # B9 — weighted confidence/severity scoring
├── taxonomy.py            # CWE/OWASP catalog + inference helpers, shared across B3/B5/B7/B9/B10
├── report.py              # B10 — bilingual PDF report generation (Playwright/Chromium)
├── run_history.py         # SQLite persistence for "Past Runs"
├── auth.py                # Session-cookie login gate (single shared admin passphrase)
└── aws_secrets.py         # Backfills secrets from AWS SSM Parameter Store at deploy time
```

---

## Running it

```bash
# Backend
python -m venv venv && venv\Scripts\activate      # or source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
git submodule update --init                        # pulls mattermost-src, scanned by B3
uvicorn api:app --reload --port 8000

# Frontend
cd ui
npm ci
npm run dev
```

Required in `.env` at the repo root (see [blocks/auth.py](blocks/auth.py), [blocks/pipeline.py](blocks/pipeline.py)):

```
ANTHROPIC_API_KEY=...
SIFTPIPE_ADMIN_PASSWORD=...
SIFTPIPE_SESSION_SECRET=...
SIFTPIPE_TARGET=mattermost        # or naviq — optional, defaults to mattermost
```

The Mattermost target additionally needs Docker Desktop running (`docker compose` in `mattermost/`); NaViQ manages its own dev server automatically once selected.

```bash
python -m unittest discover -s tests    # backend tests
cd ui && npm test                       # frontend tests
```

---

## Deployment

Not yet live. Planned: frontend on Cloudflare Pages, backend on a single AWS EC2 host behind nginx — see [docs/AWS_HOSTING_TODO.md](docs/AWS_HOSTING_TODO.md) for the infra plan and [docs/next-steps-before-deployment.md](docs/next-steps-before-deployment.md) for what's left before it ships (containerization is the current highest-leverage item).

---

## Docs

- [docs/readme-old.md](docs/readme-old.md) — the full technical checkpoint: every block's real implementation status, every bug found and fixed, session-by-session
- [docs/next-steps-before-deployment.md](docs/next-steps-before-deployment.md) — remaining work before the AWS jury deployment, including the security-hardening log (CodeQL/Dependabot setup and findings triage)
- [docs/MULTI_TARGET_PLAN.md](docs/MULTI_TARGET_PLAN.md) — how the pipeline generalized from a single hardcoded target (Mattermost) to a per-target profile system
- [docs/AWS_HOSTING_TODO.md](docs/AWS_HOSTING_TODO.md) — deployment infrastructure plan
- [docs/objetivo3_evidence/](docs/objetivo3_evidence/) — real CVEs found by the pipeline against a live target, with screenshots
