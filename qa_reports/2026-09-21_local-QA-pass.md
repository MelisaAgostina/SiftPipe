# Local QA Pass — SiftPipe containerized build

Local pass against the real containerized backend and real data (Docker Desktop/WSL2), zero AWS involved. Covered: login, target picker (Mattermost + NaViQ), Past Runs, Human Review, Correlation, and Fresh Reset (state-mutating). Result: passed — zero console errors, zero non-200 API responses across ~900+ requests observed.

Caddy crash-looped locally on its automatic-HTTPS `chmod` — traced to WSL2's DrvFs only partially emulating POSIX permissions for the Windows-hosted repo, not a SiftPipe defect (didn't reproduce in CI's native-WSL storage). Worked around by publishing the backend port directly for this pass; real HTTPS issuance stayed unverified until the deployed pass (2026-09-24), which confirmed this diagnosis.

## Findings

- **Finding 1 (FIXED):** internal backend value `"DESCARTED"` (a typo, not a real word in either language) displayed verbatim in the Correlation tab instead of "Discarded"/"Descartado". `blocks/report.py` already mapped it for the PDF report; the frontend didn't. Fixed with a display-label mapping table (`ui/src/lib/classification.ts`).
- **Finding 2 (NOT FIXED, deferred by decision):** mixed `/`/`\` path separators in one old run's stored B3 data, from before the container migration (native Windows `os.path.join` vs. the container's Linux one). Can't recur in future runs; left as-is, cosmetic only.
