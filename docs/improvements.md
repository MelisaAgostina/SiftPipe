## Where I'd invest next

Grounding this in what's actually in the repo (not already done, not already declined as out-of-scope like Approach B or pluggable LLM provider) — here's where I'd invest next, organized by your four angles. The single highest-leverage item touches both "more real" and "easier AWS deploy," so I'll flag that first.

### The one that pays off twice: containerize SiftPipe itself

There's no Dockerfile for the project — only Mattermost's own submodule Dockerfiles. Right now AWS deployment is a manual sequence (venv, playwright install --with-deps, nginx, certbot, systemd unit, git pull + reinstall on every update — see todo.md §C). A Dockerfile for api.py (Python + Playwright/Chromium deps baked in) plus a docker-compose.yml that also brings up Mattermost turns EC2 setup into "install Docker, docker compose up" instead of a multi-step manual list, and makes redeploys `git pull && docker compose up --build -d` instead of touching a systemd unit by hand. It also makes the product look more like a real deployable tool in the Informe final, not a script that only ran on your machine.

### Architecture

- **Structured logging.** main.py's `log()` currently uses `print()` with box-drawing characters (already caused one real UnicodeEncodeError bug on Windows cp1252). Swapping to Python's `logging` module with levels (and writing to a file, not just stdout) matters more once this runs headless on an EC2 box you can't watch live.
- **Fail-fast config validation.** `ANTHROPIC_API_KEY` missing today only surfaces as a crash on the first LLM call, mid-pipeline. A startup check in main.py/api.py that validates required env vars before accepting `/api/run` is cheap and reads as more production-grade.
- **Secrets via AWS Secrets Manager/SSM** instead of a hand-edited `.env` on the box — small change, but it's the kind of detail that makes the AWS deployment chapter of the Informe final look deliberate rather than "we scp'd a .env file."

### Business logic

- **B5's relevance ranking is still pure keyword matching**, while B9 got a real CWE/OWASP taxonomy engine — the readme itself flags this gap (`find_related_static_findings` "sigue siendo keywords puro"). Routing B5 through the same taxonomy B9 already has would close a gap the project's own docs already identified, which is a strong, low-risk thesis narrative ("we found this inconsistency and closed it").
- **Run-history trends.** Two separate places in readme.md §5/§7 explicitly park this as "queda fuera de este alcance, posible extensión futura." A "compare this run vs. the previous run of the same target" view (new vs. recurrent findings, severity delta) is scoped small since run_history.py already has everything needed — it's mostly a new query + a UI panel, not new pipeline logic.

### UI

- Trend/compare view in Past Runs (pairs with the business-logic item above).
- **A visible failure surface for background pipeline errors.** Several past bugs were "screen shows nothing, user has to guess why" (B3 "no findings yet", the B8 KeyError on API Error placeholders). A small toast/banner tied to run_history's error state would prevent the next version of that same class of bug from ever reaching a user again.
- A minimal empty-state/first-run guide ("pick a target → Fresh reset → Run") — worth it specifically because a jury will be clicking around cold, unlike you.

### AWS deployment ease

- Docker (above) is the big one.
- **Caddy instead of nginx + certbot** — automatic HTTPS with a ~5-line Caddyfile, meaningfully less manual TLS setup for what AWS_HOSTING_TODO.md already frames as a short-lived demo box, not an always-on service.
- A cloud-init/user-data script (or a minimal Terraform file) so EC2 provisioning is one launch instead of a manual checklist — reproducibility matters more here because the plan is spin-up → demo → tear down, not maintain forever.

---

## Objetivo 3 — Mattermost CVE validation

The thesis's actual formal objectives (not previously in this doc): a quasi-experiment on Juice Shop/MultiJuicer with ~50 LSI students comparing manual/AI/hybrid detection (Objetivo 1, already run/handled separately — not pipeline work), the hybrid pipeline operating on Mattermost as the real-environment case study (Objetivo 2, done), and validating that the winning experimental approach replicates its advantage against Mattermost specifically **because Mattermost has documented CVEs** (Objetivo 3). Juice Shop's actual role in the thesis is the controlled experiment's known-ground-truth environment — not a SiftPipe pipeline target, which is a different use of it than earlier discussion in this doc assumed.

Objetivo 3 is the direct, formally-required version of "prove substantive results" — more so than any third target below, which is supplementary the same way NaViQ was supplementary to the "generalizes" claim (neither is one of the three formal objectives).

**The gap:** `.env` currently pins `MATTERMOST_IMAGE_TAG=11.7.0` — recent enough that there's nothing documented and confirmed-disclosed for the pipeline to catch there right now (11.7.1 exists as a security-fix release, but Mattermost embargoes CVE detail for 30 days, so it isn't citable yet).

**The plan:** pin Mattermost to an older, specifically-vulnerable version for one deliberate validation run, separate from whatever version the general pipeline demo uses (same "known local disposable instance" methodology already used everywhere else in this project — just choosing the version on purpose instead of defaulting to latest).

**Chosen candidate: [CVE-2023-7113](https://nvd.nist.gov/vuln/detail/CVE-2023-7113)** — Mattermost ≤8.1.6 fails to sanitize channel-mention data in posts, allowing markup injection (CWE-79, XSS). Fixed in 8.1.7, fully disclosed (2023-12-29), not embargoed. Best fit of the options found:
- Core server, not plugin-dependent (unlike the SSRF-via-Agents-Plugin alternative below).
- Exactly B7's existing XSS detection class (`XSS_reflected`, `_looks_like_xss_payload()`/`_looks_like_html_response()`) — no new pipeline capability needed, unlike the third-target work below.

**Steps:**
1. Pin `MATTERMOST_IMAGE_TAG=8.1.6` (or another ≤8.1.6 tag) for this one validation run.
2. Find the exact injection field/syntax — not yet confirmed; needs either the [GitHub advisory](https://github.com/advisories/GHSA-h3gq-j7p9-x3p4)'s diff or live probing against the pinned instance (channel-mention data specifically, per the advisory text — likely a display-name or similar field rendered into `@mention` markup).
3. Run B3→B9 against it, confirm B7 flags it and B9 correlates it as `CONFIRMED`.
4. Switch back to 11.7.0 (or whatever version) for normal use afterward.

**Alternates, if a different vulnerability class fits better:**
- CSRF on the Calls widget — 11.0.x≤11.0.4, 10.12.x≤10.12.2, 10.11.x≤10.11.6 (CWE-352, closer to the current version line than 8.1.6).
- System Manager access-control gap — 10.7.x≤10.7.0, 10.5.x≤10.5.3, 9.11.x≤9.11.12 (CWE-284, same category as the broken-access-control detector already built).
- SSRF via the Agents Plugin ([CVE-2025-47700](https://vulert.com/vuln-db/go-github-com-mattermost-mattermost-server-238805)) — real and OWASP-relevant, but needs that plugin installed, which isn't part of the current minimal Docker setup.

### Results (2026-08-25/26)

Ran the plan above against two candidates by actually pinning `MATTERMOST_IMAGE_TAG` (and, where needed, `POSTGRES_IMAGE_TAG` for boot compatibility) in `mattermost/.env`, standing up the real vulnerable version via `docker compose`, reproducing live, then reverting to the normal `11.7.0`/`18-alpine` dev pins — same disposable-instance methodology `--mode fresh` already uses everywhere else in this project.

**CVE-2023-7113 (XSS via channel mention data) — not reproduced.** Pinned `8.1.6` (+ Postgres `13-alpine`, required for that old a Mattermost build to boot at all against the project's default `18-alpine`). Created a channel whose *display name* was a markup payload (`<img src=x onerror=alert(document.domain)>`), then referenced it via `~channel` in a post. Server-side, the post's `props.channel_mentions` does embed that display name raw/unescaped, confirming the advisory's premise. But rendering it client-side — tested via Playwright both as the channel member who created it and as a separate account with no membership in that channel (to force the "unknown channel" fallback path) — came back safely HTML-escaped in both cases, no JS dialog fired. Source inspection (`webapp/channels/src/utils/text_formatting.tsx`, `replaceChannelMentionWithToken()`) shows an `escapeHtml(displayName)` call applied uniformly regardless of where the display name came from. Mattermost never publishes patch diffs for security fixes, so there's no way to confirm whether this call predates 8.1.7 (meaning the real fix targeted some other, unidentified surface — channel header text, search-result highlighting, and notifications were considered but not live-tested) or whether the pulled `8.1.6` tag doesn't reflect the exact historical binary. Reported here as a documented negative result: the advisory's literal reading didn't hold up under direct, two-context live testing.

**CVE-2025-3611 (System Manager access-control gap) — root cause confirmed live.** This one has an actual public fix commit, `mattermost/mattermost@6f33b721de76`, unlike the XSS case. The bug: `server/public/model/role.go`'s `SysconsoleAncillaryPermissions` map — which auto-grants "ancillary" permissions alongside each System Console permission when a built-in role is seeded — incorrectly bundled `PermissionViewTeam` under `PermissionSysconsoleReadReportingTeamStatistics` (the "Reporting → Team Statistics" toggle), when `view_team` should only ever have come from `PermissionSysconsoleReadUserManagementTeams` (the actual "Teams" toggle). Net effect: an admin who explicitly sets Teams to "No access" but leaves Team Statistics reporting on doesn't actually revoke team-viewing rights, because they were never really tied to the Teams toggle. Pinned `10.7.0` (+ Postgres `16-alpine`) and queried the freshly-seeded, untouched `system_manager` role via `GET /api/v4/roles/name/system_manager` *before touching anything* — its shipped permission list does contain both `sysconsole_read_reporting_team_statistics` and `view_team` together, exactly matching the vulnerable mapping, directly on the live affected binary. The one thing not completed: driving the full exploit end-to-end (a restricted System Manager account actually pulling team data via direct API) needs Mattermost's Enterprise "Delegated Granular Administration" feature, which is license-gated — confirmed blocked both in the System Console UI (trial-license upsell page instead of the role editor) and via the API (`PUT /api/v4/users/{id}/roles` → `"Custom Permission Schemes not supported by current license"`). Getting a trial license was considered and skipped — it means sending real account info to Mattermost's external license server for a supplementary validation step, judged not worth it.

**Screenshots/evidence:** [`objetivo3_evidence/`](objetivo3_evidence/) — `cve-2023-7113_member_view.png` and `cve-2023-7113_nonmember_view.png` (rendered, escaped mention link in both viewer contexts), `cve-2025-3611_license_gate.png` (the Enterprise upsell blocking the full exploit demo).

**For the thesis:** CVE-2025-3611 is the stronger result — a real, disclosed, CVE-numbered vulnerability with its root cause pinpointed to one exact map entry in one exact commit, independently reproduced by direct inspection of the live server's own seeded role data on the affected version, not just by trusting the advisory's prose. CVE-2023-7113 stands as an honestly-reported negative: a plausible, advisory-consistent hypothesis, tested rigorously (two viewer contexts, server- and client-side, source-level confirmation of the sanitizing call), that didn't hold up — itself a fair methodological point about the limits of working from a terse public advisory without a private patch diff. Mattermost was reverted to `11.7.0`/`18-alpine` afterward; verified the original dev data (admin/seed accounts, dated well before this session) survived untouched throughout.

### Closing the loop: does the pipeline itself catch CVE-2025-3611? (2026-08-26)

The results above establish *ground truth* — that the vulnerability is real and locatable — but not the thesis's actual Objetivo 3 claim, which is about **el comportamiento del pipeline**: does SiftPipe's own reasoning, not manual investigation, replicate the detection. That gap is worth closing directly rather than assumed either way, especially since every pipeline run costs real API money and B4/B7 (dynamic testing) can't reach this specific bug at all — full exploitation needs Mattermost's licensed Enterprise role editor, already established above as unavailable. B3 (static analysis) was the only block with a real shot, since it only needs source code, not a running licensed instance.

**Before spending anything, checked whether a normal B3 run could even reach the file.** It could not, for two independent reasons, both fixed:

1. **`blocks/static_scanner.py`'s directory targeting was badly miscalibrated.** Replicated its exact file-selection logic against the real `mattermost-src` tree: of 2,057 candidate files, 2,012 (97.8%) came from `server/`, while `webapp/` — the entire React frontend, including `utils/text_formatting.tsx` where the CVE-2023-7113 escaping logic actually lives — contributed only 16 files, every one of them an accidental match on a folder named `store` (Redux boilerplate). Not one real component/action/util file was reachable. Meanwhile non-application tooling (`e2e-tests/`, top-level `api/` OpenAPI doc-generation, `tools/`, and `.github/actions/` CI scripts) was passing the filter and eating scan budget. Fixed `DEFAULT_EXCLUDE_DIRS`/`DEFAULT_RELEVANT_DIRS` in `static_scanner.py` and the matching `MATTERMOST` profile in `blocks/targets.py`, rebuilding the relevant-dirs list from directory names actually verified to exist in the repo rather than a generic starter list. Re-verified against the live tree afterward: 5,314 candidates, properly split 3,622 `webapp/` / 1,692 `server/`.
2. **`main.py`'s `MAX_FILES = 10` cap.** Even fixed, `role.go` ranks #1,408 of 5,314 in scan order — a normal run still wouldn't reach it. Left this constant unchanged (out of scope for what was asked) but it's the reason a full run was never attempted for this test.
3. **The prompt itself was widened**, per request, within the same 4 existing OWASP categories (no new categories added) — each of A05/A01/A02/A07 gained several concrete sub-patterns. A01 in particular now explicitly names the exact bug class CVE-2025-3611 is: a permission incorrectly bundled into an unrelated config/data structure, not just a missing route decorator.

**The actual test, kept to one paid API call.** Fetched Mattermost's real `v10.7.0` tag into an isolated git worktree (sparse-checked-out to just `server/public/model/`, avoiding Windows path-length errors elsewhere in the tree) — confirmed the vulnerable pattern was present (`PermissionViewTeam` still listed under `PermissionSysconsoleReadReportingTeamStatistics` at line 112, exactly as in the pre-fix commit). Ran B3's real `get_analysis_prompt()`/`ask_llm()` — same `claude-haiku-4-5` model, same prompt, same post-filter the real pipeline uses — against that one file only, so the test cost exactly one call.

**Result: B3 did not catch it.** The raw response was an empty array. This wasn't a truncation artifact — both halves of the duplication (the legitimate entry at line 74, the buggy duplicate at line 112) are well inside the 15,000-character window the file gets truncated to, confirmed by checking their line numbers directly. The model had the actual bug fully in view, with a prompt that explicitly describes this exact pattern, and still returned nothing. Most likely explanation: B3's finding schema (`"line": N, "evidence": "exact snippet"`) is built for single-location defects. This bug isn't at one line — it's a relationship between two map entries 37 lines apart, which requires holding two locations in mind and comparing them, a different and harder task than spotting something locally obvious. `claude-haiku-4-5` (chosen for B3 specifically for cost, not reasoning depth) most likely isn't reasoning that far unprompted, regardless of category-level guidance.

Cleaned up fully afterward: worktree removed, fetched tags deleted, `mattermost-src/mattermost` verified back at its original commit with a clean working tree.

**Evidence:** [`objetivo3_evidence/b3_scoped_scan_role_go.json`](objetivo3_evidence/b3_scoped_scan_role_go.json) — raw LLM response, prompt length, and content length sent, sufficient to cite directly.

**For the thesis:** this is the actual Objetivo 3 result for this CVE, not a substitute for it — the pipeline's own static-analysis reasoning, tested directly and fairly against the confirmed root cause with every setup obstacle removed, did not independently detect it. That's a concrete, well-isolated boundary of what B3 as currently built can catch (cross-location config-consistency bugs), established for the cost of one API call instead of guessing or skipping the test. Directly usable as an honest limitations finding: SiftPipe's hybrid approach still needed the human-driven investigation (this session's manual root-cause work) to establish what a pure static pass on a small, cheap model missed.

---

## Scoping a third target — supplementary, not a formal objective

Not required by the thesis's actual three objectives (see above) — this is "extra evidence of substantive results" in the same spirit NaViQ was extra evidence of generalization, not a graded deliverable on its own. Two real candidates are now both fully investigated; below is what committing to each would actually take.

### TC_Grupo9 (your own NestJS/Prisma/Postgres project)

**Confirmed findings so far:** `sp_update_perfil_usuario` references a nonexistent table (`usuarios` vs `auth.usuario`) — near-certain real `500`, though B7 will mislabel it `SQLi`. The `ordenCol` gap turned out *not* to be SQLi (static `CASE` branches in the procedure, not dynamic SQL) — just a silently-unsorted-results bug, low severity. The recovered `pg_dump` itself (real bcrypt hashes + names/emails under `/docs`) is a plausible B3 hardcoded-credentials finding if that path is in scan scope.

**To stand it up:**
- New `TargetProfile` (`blocks/targets.py`): `source_dir="apps/server/src"`, `source_extensions=(".ts",)`, exclude `node_modules`/`dist`/`test`.
- Restore the DB from the recovered `pg_dump` (needs a local Postgres instance) — schema, all 43 procedure bodies, and seed data come back in one shot.
- No test credentials documented anywhere — need to register one via the real signup flow, or seed one directly from the restored DB.
- **Open decision that changes real testable surface:** target `apps/server` alone (JSON API — XSS untestable, B7's own content-type guard correctly won't flag a JSON echo), or `apps/server` + `apps/client` (React 19/Vite — modern SPA, lower crawl risk than Juice Shop's older Angular routing, reopens real XSS as testable).
- No fresh-reset story built yet (Mattermost/NaViQ each have one) — would need one for a repeatable "restore to known state" run.

### lutto_website (PHP/CodeIgniter4)

**Confirmed finding:** `consultas/leido`/`consultas/noleido` GET routes have zero auth filter while every sibling admin route in the same file (`Routes.php`) has `authAdmin` — verified against the real `AuthFilter` class too. This is a direct, high-confidence hit for the GET-link action-probe detector already built (SESSION 13) — built specifically because of this bug.

**To stand it up:**
- New `TargetProfile`: `source_dir="app"` (Controllers/Models/Views), `source_extensions=(".php",)`, exclude `vendor`/`system` (framework code, not first-party).
- DB restore is trivial — `db_lezcanoairaldi_m.sql` is already sitting in the repo, a straightforward MySQL import.
- Test credentials already known and working: `admin`/`123456`, `cliente`/`123456` (`USUARIOS-TEST.txt`).
- Login form field selectors not yet verified live (haven't opened the actual login view template) — small, same-shape task as NaViQ's Phase 0.
- No client/API scope ambiguity — single monolithic server-rendered app.
- Unexplored surface: `ventas_controller.php`/`carrito_controller.php` (sales/cart) not yet reviewed, possible additional findings. `vendor/` is tracked in git despite being gitignored — unchecked whether it holds a stale/vulnerable dependency version (OWASP A03).

### Where this leaves it

lutto_website is lower-effort (test creds in hand, DB import is a one-liner, no client/API ambiguity) and higher-certainty (one confirmed, high-confidence finding that a just-built detector directly targets). TC_Grupo9 is the harder target precisely because it's more competently built — a genuine "we tried and it mostly held up" result, which is also valid evidence, just a different kind. Both remain real options; the actual pick is still open.