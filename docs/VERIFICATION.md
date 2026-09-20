# Verification report — 19 September 2026

Historical checkpoint. For the subsequent Gemini fix, member workspaces and current
test results, see [20 September continuation](CONTINUATION_2026-09-20.md).

Scope: the recovered application on `codex/company-knowledge-mvp`. Linux x86-64,
Python 3.12.14, Node 24.19.0. No customer documents or live Gemini credentials were
used. Windows commands are documented but have not been executed on Windows.

## Final results

| Check | Exact result | What it establishes |
| --- | --- | --- |
| Clean Python environment installed from `requirements-dev.txt` | Pass | Pinned backend/development dependencies install on this Linux/Python combination. |
| `RUN_SEMANTIC_TESTS=1 python -m pytest -q` in that clean environment | **60 passed, 7 skipped, 2 warnings** | 52 API/unit/safety cases plus 8 actual semantic/model cases pass. The 7 skipped cases are live Gemini. |
| `python -m ruff check app scripts tests` | All checks passed | Configured Python static checks. |
| Frontend `npm ci` | Pass | Lockfile install is reproducible here. |
| Frontend `npm run lint` | Pass | ESLint checks pass. |
| Frontend `npm run build` | Pass | Vite 8.1.5 production bundle builds. |
| Frontend `npm run test:e2e`, with the Chromium executable override | **3 passed** | Real desktop/mobile browser, React, Vite proxy, HTTP, PDF parsing, SQLite and local retrieval; answer generation is a test double. |
| `python -m pip_audit -r requirements.txt` | **0 known vulnerabilities across 50 dependencies** | Point-in-time advisory audit, not a security proof. |
| Frontend `npm audit` | **0 vulnerabilities** | Point-in-time audit including development dependencies. |
| `git diff --check` and staged whitespace check | Pass | No reported whitespace errors. |
| Tracked/staged path and secret-signature review | Pass | No real credentials, private documents, environments, dependencies, models, uploads or generated test/build output selected for commit. The only PDF is the synthetic fixture. |

The two pytest warnings are upstream Starlette/httpx TestClient and AnyIO
BlockingPortal deprecations. Neither failed a test. No numerical coverage claim is
made. Earlier 48/56-test checkpoints are superseded by the final 60-pass result.

## Components and boundaries

| Area | Real components exercised | Replaced or unverified |
| --- | --- | --- |
| API/ingestion/safety tests | FastAPI/ASGI, multipart, pypdf subprocess, chunker, SQLite, validation and error handling | Most API tests substitute deterministic embeddings and an answer test double to isolate behavior. |
| Semantic suite | Revision-pinned BGE/FastEmbed/ONNX, actual 384-dimensional vectors, synthetic PDF parsing, exact cosine retrieval | No live answer generation. |
| Provider contract tests | Actual `GeminiAnswerer`, Google SDK configuration classes, response schema and server-side validation | SDK client responses/failures are simulated; no network call to Gemini. |
| Browser suite | Chromium 153.0.8010.0, React, Vite proxy, production app factory, PDF extraction, local model, database, download/delete | Explicit test-only answer generator; this is not proof of Gemini answer quality. |
| Production server smoke | Real Uvicorn over TCP, production `app.main:app`, actual model/parser/store | Key intentionally absent; supported generation therefore returns controlled 503. |

The model revision is `52398278842ec682c6f32300af41344b1c0b0bb2` for
`BAAI/bge-small-en-v1.5`. Five questions ranked the expected physical page first:

| Question/topic | Expected and observed first page |
| --- | --- |
| Casual leave allowance | 1 |
| Deadline for submitting reimbursement receipts | 2 |
| Stolen work computer: who to tell | 4 |
| Who assigns a new employee's buddy | 5 |
| What happens after a client signs an agreement | 3 |

These are five synthetic topic checks, not a representative business benchmark.
The real model retrieved no qualifying evidence for “What is the capital of
France?”, so the production answer path abstained without contacting Gemini.
Related but missing policies can pass retrieval; their refusal still depends on
live model behavior and remains a live evaluation gate.

## Critical cases covered

- Valid/multipage PDFs, physical page metadata, normalization and chunk coverage,
  offsets and overlap; invalid types/signatures, malformed, zero-page, blank/scanned,
  encrypted, oversized and too-many-page files.
- Unsafe filenames, content deduplication, same-name conflicts, persistence across
  app instances, quotas, atomic failure cleanup, download and cascade deletion.
- Authentication before parsing, CORS, bounded bodies without Content-Length,
  extraction timeout, rate limits, private response headers and sanitized failures.
- Missing embedding model, model identity mismatch, absent Gemini key and simulated
  provider failures/invalid output; document deletion during answer generation.
- Unknown source IDs, invented quotations, unsupported numeric values, blank claims
  and whitespace-only quote bypass; valid source/document/page attribution.
- Worker application-secret stripping and hardening of existing Unix data-directory
  permissions. Separate workspace directories are tested; multi-tenant SaaS is not.

## Production HTTP smoke results

The production server ran from the clean environment against an isolated temporary
workspace and the real embedding files, without a Gemini key:

| Operation | Result |
| --- | --- |
| `GET /health` | 200 |
| Unauthenticated `GET /documents` | 401 |
| `POST /read-pdf`, synthetic handbook | 200; 5 physical pages |
| `POST /upload`, same handbook | 201; 5 pages, 5 chunks |
| Supported leave question without provider key | 503; `provider_not_configured` |
| Unrelated geography question | 200; `insufficient_evidence`; empty sources |
| Delete document | 204 |
| List after deletion | 0 documents |

The environment initializer was also executed in a disposable copied setup: exit 0,
43-character random workspace token, blank Gemini key, Unix mode 0600, no token in
stdout/stderr. A second invocation refused to overwrite the existing file.

## Browser validation

The normal Playwright Chromium download timed out in this environment. One
alternative succeeded: a Chromium binary from `@sparticuz/chromium`, installed and
extracted only under ignored temporary tooling. It is not a product dependency or
committed artifact. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` selected that executable.

All three scenarios passed:

1. Upload → real retrieval → test answer → page/quote citation → source download;
   simulated provider outage with request reference; insufficient-evidence display;
   duplicate upload and deletion. No browser page errors in this workflow.
2. Wrong-token feedback, invalid PDF feedback, workspace locking and cleared token.
3. Suggested question and source display at 390×844; no horizontal page overflow;
   deletion after the mobile flow.

Desktop/mobile screenshots were visually inspected. Browser testing used Chromium
only, not Firefox, Safari, an actual mobile device, Windows, or the live provider.
The clean Python environment and browser fixture environment were tested separately.

## Live Gemini gate

**7 live tests skipped; no live Gemini success is claimed.** `GEMINI_API_KEY` was
unavailable and `RUN_LIVE_GEMINI` was not enabled. The seven opt-in cases cover three
supported policies, two absent benefits, a prompt-injection attempt and a personal
expense question. With opt-in but no key, the suite fails rather than silently skips.

Use the Windows commands in [the handoff](HANDOFF.md) to run them with a locally
configured key. Provider validity, availability, actual structured-output compliance,
answer quality, latency and cost remain unverified here. Source validation checks
provenance and some numeric errors; it cannot prove every claim is entailed.
