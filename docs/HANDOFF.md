# ClarityOps AI — work-cycle handoff

19 September 2026. This extends the recovered application; it is not a replacement
project. [Exact validation results](VERIFICATION.md) and [security review](SECURITY.md)
are part of this handoff.

## A. Verified current product state

A runnable single-company knowledge-assistant MVP exists. Safe PDF ingestion,
persistent local semantic search, document management and the React workflow work
with real local components. Grounded generation and its failure/attribution contract
are implemented and tested with simulated provider responses. Live Gemini answer
quality is **unverified**, so the complete real-provider vertical slice is not yet
accepted. No public deployment or commercial pilot is running.

## B. Implemented

- Reproducible backend/development dependency locks, environment template, private
  setup helper, lazy Gemini initialization and accurate run commands.
- Authenticated, bounded PDF ingestion; page-aware extraction and chunking; explicit
  handling for invalid, encrypted, empty/scanned and oversized PDFs.
- Local embeddings, transactional SQLite documents/chunks/vectors, deduplication,
  filename conflict protection, persistence, downloads and deletion.
- Evidence-only generation, structured claims, validated source IDs/quotes/numeric
  values, source/page metadata and explicit insufficient-evidence responses.
- React workspace unlock, upload/status/list, questions, answers, quoted citations,
  downloads/deletion and useful errors; desktop/mobile browser validation.
- Synthetic five-page handbook, API/safety/semantic/provider/browser tests and runbook.

## C. RAG architecture

The existing React/Vite UI reaches FastAPI through a same-origin development proxy.
A shared workspace token is checked before request parsing. Validated PDFs are
extracted by a bounded subprocess. Normalized page-local chunks have document/chunk
IDs, physical page and character offsets. The pinned BGE small English model produces
384-dimensional embeddings locally. SQLite commits the original PDF and index rows
atomically. Questions use local cosine retrieval (up to five chunks). Gemini receives
the question and evidence, then the server validates its structured claims and attaches
citations from trusted metadata. With no qualifying evidence it abstains without an
LLM call. Details and tradeoffs: [architecture](ARCHITECTURE.md).

## D. Files/components changed

| Component | Files |
| --- | --- |
| API, configuration and access | `backend/app/main.py`, `config.py`, `security.py`, `errors.py` |
| Ingestion, index and retrieval | `documents.py`, `pdf_worker.py`, `store.py`, `embeddings.py` |
| Gemini and provenance | `backend/app/gemini_service.py` |
| Reproducibility | `.gitignore`, `backend/.env.example`, `requirements*.in/txt`, `pyproject.toml`, `backend/scripts/` |
| Backend verification | `backend/tests/` including explicit semantic/live markers and test-only browser server |
| Frontend | `App.jsx`, `api.js`, styles, `index.html`, favicon, Vite configuration, package manifest/lock |
| Browser verification | `frontend/playwright.config.js`, `frontend/e2e/workflow.spec.js` |
| Demo and documentation | `samples/Meridian_Works_Handbook.pdf`, root/frontend READMEs, `docs/` |

Unused starter artwork was removed after confirming no references. The original
FastAPI routes remain, with safer behavior. `/ask` retains its `response` alias.

## E–F. Tests and real-versus-simulated boundary

- **60 backend tests passed, 7 live tests skipped, 2 upstream deprecation warnings**
  in a fresh Python environment installed from the pinned development requirements.
- **3 Playwright scenarios passed**; frontend lint/build and Python Ruff passed.
- Python audit: **50 dependencies, 0 known vulnerabilities**. npm audit: **0**.
- Real production Uvicorn/TCP smoke: health 200; unauthenticated documents 401;
  PDF extraction 200/5 pages; ingestion 201/5 chunks; missing-key answer 503;
  unrelated-question refusal 200/no sources; deletion 204/empty subsequent list.
- Actual pypdf, SQLite and BGE/FastEmbed/ONNX were exercised. Five semantic topic
  questions placed the correct page first. Most isolated API tests use deterministic
  embeddings; provider contract tests simulate SDK responses. Browser tests use real
  retrieval and a clearly separate test-only answer generator.
- Setup helper, PDF fixture rendering, screenshots, staged paths, whitespace and
  secret signatures were checked. The [verification report](VERIFICATION.md) records
  cases and limitations; no broad benchmark or penetration-test claim is made.

## G. Live Gemini status

No key was available; **all seven live tests remain skipped**. Nothing was weakened
to pass them and no key was committed. The gate needs a secure local key and explicit
opt-in. Missing-policy refusal with related evidence, actual answer quality, SDK/model
network compatibility, provider quota/latency and usage cost are not verified here.

## H. Browser/E2E status

The standard browser download timed out. A single alternative Chromium installation
succeeded; Chromium 153.0.8010.0 passed the three desktop/mobile scenarios. No repeated
download loop is required. The browser path override is optional local tooling, not a
runtime dependency. Firefox/Safari, Windows and live-provider browser E2E are untested.

## I. Security issues fixed

Raw-filename traversal, unrestricted uploads, missing access checks, unbounded parser
execution, raw exception leakage, partial storage/deletion, permissive request handling
and uncontrolled generic answers were addressed. Final review also hardened existing
Unix data-directory permissions and removed application secrets from the PDF worker's
environment. Frontend dependency advisories were resolved in the lockfile. Tokens stay
in browser memory; Gemini keys stay on the backend. Git excludes runtime/private data.

## J. Known limitations

English text PDFs only; no OCR. Complex layouts/tables, cross-page policy context and
conflicting document versions need more evaluation. Retrieval thresholds were checked
on the synthetic fixture, not tuned on a business corpus. Quotes do not mathematically
prove claim entailment, and numeric checks do not cover all number representations.

One company/process/database and a shared token: no user accounts, RBAC, tenant routing,
document ACLs, encryption-at-rest, managed backups, production monitoring or billing.
All token holders can delete. The parser subprocess is not an OS sandbox; Windows
memory caps are not implemented. Deletion cannot erase downloads, backups, prior
browser answers or evidence already sent to Gemini. Legacy `backend/uploads` files
are neither imported nor deleted automatically. No real customer data should be used
until the private-pilot gates below are addressed.

## K. Exact Windows local run instructions

Prerequisites: Git, Python 3.12, Node.js 22.12+ and npm. These commands are for a fresh
checkout; use your existing checkout instead if you already have the development
branch. Do not overwrite another working tree with uncommitted work.

```powershell
git clone --branch codex/company-knowledge-mvp https://github.com/harideep05-cmd/clarityops-ai.git
cd clarityops-ai
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\init_env.py
notepad .env
```

In this local file, set `GEMINI_API_KEY` to your existing key. Keep the generated
`CLARITYOPS_ACCESS_TOKEN`; copy **that workspace token** into the browser unlock form.
Never paste the Gemini key into chat, the browser form, frontend variables or Git.
If `.env` already exists, the helper leaves it unchanged: use `.env.example` to add
missing variables locally. Existing process environment variables take precedence.

Then, still in `backend`:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_embeddings.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In a second PowerShell window, change to your repository root, then:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open `http://127.0.0.1:5173`. A third terminal can check liveness with:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expect `status: ok`. Keep both servers bound to loopback. Stop them with Ctrl+C.
These commands avoid PowerShell activation-script execution-policy issues. The
Windows command path is reviewed, but Windows runtime compatibility is unverified.

## L. Test locally using your existing Gemini key

1. Complete K and restart the backend after changing its `.env`.
2. Unlock with the workspace token and upload the synthetic handbook. Ask the
   questions in M; inspect the quoted evidence, not just the answer text.
3. In another terminal at `backend`, run the repeatable checks below. Live checks
   send synthetic text to Gemini and use your provider quota; they can incur charges.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:RUN_SEMANTIC_TESTS="1"
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:RUN_SEMANTIC_TESTS
$env:RUN_LIVE_GEMINI="1"
.\.venv\Scripts\python.exe -m pytest -m live -q
Remove-Item Env:RUN_LIVE_GEMINI
.\.venv\Scripts\python.exe -m ruff check app scripts tests
```

The first pytest command should reproduce 60 passes/7 live skips. The second should
run **7 live cases**; its result is an acceptance gate, not guaranteed in advance.
Do not suppress or reinterpret failures. A 503 indicates missing configuration; a
502 indicates provider failure/unusable response. Use the request reference to
correlate safe backend diagnostics; do not share secret files or private payloads.

From `frontend`, for the separate browser integration suite:

```powershell
npm.cmd run lint
npm.cmd run build
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

These tests start their own isolated servers on ports 18000/15173 and use a test
answerer regardless of your Gemini key. Leave those ports free. To use a compatible
existing Chromium if download is blocked, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to
its full executable path before the last command.

## M. MVP demo script

Upload `samples/Meridian_Works_Handbook.pdf` and wait for Ready (five pages).
Ask casual leave allowance (12 days, page 1), reimbursement deadline (14 calendar
days, page 2), and what to do about a lost laptop (IT service desk, page 4). Verify
each quote and page. Ask parental-leave allowance: it is absent, so expect refusal
with no sources. Re-upload to show deduplication, download a source, then delete the
document and verify the list is empty. [Full five-minute script](DEMO.md).

These are live-demo expectations, not results observed with Gemini in this environment.

## N. Before a private business pilot

Pass live-provider tests and review answers on an approved, non-sensitive evaluation
set, including near matches, conflicting policies and malicious instructions. Define
company boundaries and employee/owner access. Prepare private TLS hosting, resource
limits, encrypted storage, backup/restore and operational monitoring. Agree on permitted
data, Gemini processing/retention, deletion expectations and a human policy owner.

Next three product tasks, in priority order:

1. Close the live-Gemini acceptance gate and measure answer correctness, source support
   and refusals on a realistic evaluation set.
2. Add owner/employee identity and access rules with explicit company isolation before
   onboarding any second company or confidential documents.
3. Validate one narrow business pilot workflow in a private, monitored environment,
   with backup/restore and data-handling agreements in place.

## O. Git branch and commit state

Development branch: `codex/company-knowledge-mvp`. Original main/base:
`2f67311b881b0e769a39886ca8439a97354d836c`. The recovered audit/reproducibility commit
is `97abfd2`; backend implementation is `c079be1` and the frontend/browser workflow
is `78045a1`. This documentation is a subsequent commit. The final execution handoff
records the published tip. These hashes identify the preserved local checkpoints.
Terminal Git has no push credentials here; publishing through the connected GitHub
integration assigns new commit IDs. Publication is verified by matching the complete
Git tree hashes, while preserving the original local history. Inspect the history in
your checkout with:

```powershell
git status --short --branch
git log --oneline main..HEAD
git rev-parse HEAD
```

No merge into main, force push, history rewrite, visibility change, public deployment
or paid infrastructure creation is part of this cycle.

## P. Review/merge assessment

**Ready for code review as a local MVP. Hold acceptance of the complete Gemini
vertical slice until the seven live tests and manual evidence review pass.** This
is not a recommendation to expose the app publicly or accept customer data. Main
must be merged only by the owner after review; it was not merged by this work cycle.
