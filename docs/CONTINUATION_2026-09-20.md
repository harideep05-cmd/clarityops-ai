# Continuation verification and handoff — 20 September 2026

This continues `codex/company-knowledge-mvp` from published commit `1c06282`
(Gemini response-schema compatibility). The interrupted work survived: the local
Gemini-hardening commit plus uncommitted company access, storage, UI and runbook
changes. Neither checkout was reset, and the original MVP was preserved.

## Verified product state and changes

- The original local demo remains available. Opt-in `members` mode adds isolated
  company knowledge stores and owner/employee access derived from the identity
  registry, never a workspace/role header or other client selector.
- Owners upload/index/delete PDFs and issue/revoke member credentials. Employees
  list documents, ask questions, inspect page/quote citations and download sources.
  Unauthorized employee writes are rejected before request bodies are read.
- Member credentials contain 256 random bits, are stored as SHA-256 hashes, expire
  within 30 days, and can be revoked. Bootstrap/recovery is local-operator-only and
  writes credentials to an exclusive private file, never terminal output.
- Document creation/deletion and membership changes create transactional,
  company-scoped management events. Uploader metadata is preserved with documents.
- Gemini schemas retain the `1c06282` compatibility fix. Local parsing rejects
  unexpected/missing fields, malformed JSON/claims, duplicate keys and type coercion.
  Provider 429 becomes a safe quota/rate-limit response without automatic retries.
- The UI exposes owner/member controls, hides employee write controls and returns
  expired/revoked users to unlock. Final review also fixed stale asynchronous results:
  a response from a locked token cannot populate a different company's workspace.
- Configuration rejects private deployment with shared-demo authentication or
  non-HTTPS CORS origins. This is a configuration guard, not deployed TLS.

The RAG pipeline remains PDF validation, bounded extraction, page-local chunks,
local 384-dimensional BGE embeddings, SQLite storage, scoped cosine retrieval,
Gemini structured claims and server-side citation/quote/numeric validation.
No remote embedding service, distributed vector database or new paid infrastructure
was introduced.

## Exact final results

Environment: Linux x86-64, Python 3.12.14, Node 24.19.0, Chromium 153.0.8010.0.
Existing pinned dependency definitions and the public pinned embedding model were
retained. No real company documents or live provider credentials were used.

Final backend command, from `backend`:

```sh
GEMINI_API_KEY= RUN_LIVE_GEMINI=0 RUN_SEMANTIC_TESTS=1 .venv/bin/python -m pytest -q -ra
```

**132 passed, 7 skipped, 0 failures, 2 deprecation warnings; 9.39 seconds.**
The warnings concern Starlette's httpx TestClient and AnyIO BlockingPortal aliases.
They are dependency migration notices, not failed application assertions.

| Backend suite | Passed | Skipped | Principal coverage |
| --- | ---: | ---: | --- |
| `test_answers.py` | 17 | 0 | Grounding, attribution, numeric/quote rejection, controlled errors and log redaction |
| `test_ingestion.py` | 20 | 0 | Validation, extraction, chunking, atomic persistence, duplicates, deletion and limits |
| `test_memberships.py` | 36 | 0 | Company boundaries, owner/employee rules, expiry/revocation, migration, recovery and cold restore |
| `test_provider_schema.py` | 35 | 0 | Strict response parsing, real SDK serialization with offline transport, quota handling |
| `test_security.py` | 15 | 0 | Authentication, request boundaries, CORS, limits and safe errors |
| `test_semantic.py` | 9 | 0 | Real local retrieval, page ranking, model failure/mismatch and concurrent company isolation |
| `test_live_gemini.py` | 0 | 7 | Explicitly skipped; no live Gemini calls |

Other completed checks:

| Check | Result |
| --- | --- |
| `.venv/bin/python -m ruff check app scripts tests` | Passed |
| `npm run lint` | Passed |
| `npm run build` | Passed; 19 modules; final JS 205.97 kB / 64.78 kB gzip |
| `npm run test:e2e` with existing Chromium executable override | **6 passed**, 0 failed; 15.4 seconds |
| Python dependency audit | 50 production dependencies, **0 known vulnerabilities** |
| npm dependency audit | **0 known vulnerabilities**, including development dependencies |
| `git diff --check` | Clean |

The dependency audits completed before interruption on the same unchanged lockfiles;
their saved JSON results were checked on resumption. No dependency changes required
a redundant reinstall/audit. Backend and browser suites were rerun for the final gate.
After the UI race fix, frontend lint/build and all six browser scenarios passed again.
No backend source changed after the final 132-test pass.

Browser scenarios cover the original upload/ask/citation/refusal/download/delete
workflow; authentication and invalid uploads; mobile layout; owner-issued employee
access, mobile employee querying/download and revocation; cross-company access denial;
and a delayed answer crossing a lock/unlock boundary. Standard browser download had
previously timed out; a working existing Chromium binary was reused. Firefox, WebKit
and the new Windows member workflow were not executed here.

An earlier production-Uvicorn TCP smoke check in this same work cycle used the real
`app.main:app`, local embeddings, SQLite and synthetic PDFs, without a Gemini key:

| Operation | Observed result |
| --- | --- |
| Liveness / unauthenticated document request | 200 / 401 |
| Owner upload | 201; 5 pages, 5 chunks |
| Employee original-PDF download | 200 |
| Employee deletion | 403 |
| Other company downloading that document ID | 404 |
| Supported question without provider key | 503 `provider_not_configured` |
| Unrelated question | 200 `insufficient_evidence`, empty sources |
| Owner deletion | 204 |

## Real components versus test doubles

Real components exercised: FastAPI request/permission paths, pypdf subprocess
extraction, SQLite transactions, identity hashing/expiry/revocation, metadata
migration, pinned FastEmbed/ONNX model, retrieval, production Uvicorn, React/Vite and
Chromium. Five handbook topics ranked their expected page first. Six concurrent
queries against two different synthetic policies returned the correct company's
evidence using the real embedding model.

Most unit/API tests use deterministic embeddings and a test answerer for predictable
failure cases. The semantic and browser suites use real embeddings but a synthetic
answer generator. The offline schema test uses the real Google SDK and HTTP
serialization with `httpx.MockTransport`, not Google's live service. The delayed
browser-response test holds a real test-server response in transit; it does not
substitute a live Gemini answer.

The owner reported seven live Gemini passes and a Windows browser demonstration on
`1c06282`, followed by free-tier quota exhaustion. Those are prior owner-reported
results. This continuation does not claim live Gemini verification of the new commit.
All seven live tests remain opt-in. Do not repeatedly run them after a quota failure.

## Migration, compatibility and security boundaries

The additive migration introduces nullable `created_by` metadata and management
events. Its regression fixture now includes the old document AND chunk schema:
PDF bytes, IDs, chunk/vector bytes, embedding model identity, page metadata,
deduplication and retrieval survive two startup cycles without reindexing.

Existing demo data stays in `data/knowledge.sqlite3`. Member mode starts separate
empty company stores; it neither imports nor exposes the shared collection. Tests
verify member mode cannot read legacy IDs and switching deliberately back to local
demo mode still finds the original data. There is no automatic company assignment.

The backup test copies/restores the whole stopped data root and verifies identity,
PDFs, employee restrictions and company isolation. It does not implement encrypted
backups or revocation reconciliation. An older snapshot can revive tokens revoked
after the snapshot: access must stay closed until the operator reconciles them.

Security review covers forbidden artifact paths and credential signatures in the
files proposed for publication, including the earlier local Gemini commit. The only
tracked PDF remains the existing synthetic sample. Generated credentials, environment
files, databases, model cache, browser artifacts and dependency installations remain
ignored. No secret values are included in verification output.

Remaining limits: application-level isolation in one process, shared provider/server
capacity, bearer credentials without MFA/SSO, no document-level ACLs, 20 company and
100 member-record caps, no OCR, no retention automation, no tamper-evident/read audit,
no managed encryption/backup/monitoring, and no proof of natural-language entailment.
Quote/numeric checks reduce fabrication; live policy and adversarial evaluations
remain necessary before making commercial reliability claims.

## Files and local acceptance

Key backend changes: `app/gemini_service.py`, `app/identity.py`, `app/workspaces.py`,
`app/security.py`, `app/main.py`, `app/store.py`, `app/config.py`, `app/embeddings.py`,
`scripts/pilot_admin.py`, `.env.example` and their regression tests.
Key frontend changes: `src/App.jsx`, `src/Members.jsx`, `src/api.js`, `src/App.css`,
Playwright projects/member scenarios and the test-only backend launcher.
README, architecture/security notes and the new pilot runbook describe the implemented
behavior and explicitly separate it from future hosting/pilot work.

Follow the [Windows setup](../README.md#setup-and-run-windows-powershell) and
[member operator runbook](PILOT.md). Keep the existing Gemini key in the local ignored
backend environment; do not paste it into chat, GitHub or the browser unlock form.

Local acceptance sequence:

1. Provision a synthetic company with the helper and enable `members` mode.
2. Unlock as owner, upload the existing synthetic handbook, and issue employee access.
3. In a second browser profile, unlock as employee. Ask the casual-leave question;
   with available Gemini quota, verify 12 days, page 1, a supporting quote and download.
4. Ask about parental leave and verify insufficient evidence. Stop if quota is exhausted.
5. Confirm employee upload/delete controls are absent and the API denies writes.
6. Revoke that employee; their next request should return to unlock.
7. Provision a second synthetic company and verify an empty collection and denial of
   the first company's source ID. Restart and verify persistence.

Before the first business: complete Windows member-flow acceptance and a quota-aware
real Gemini check; prepare approved private TLS/network access, restricted service
accounts, encrypted storage/backups, restore reconciliation, monitoring and incident
procedures; agree allowed data and provider/retention terms with the pilot owner.

**Highest-priority next engineering task:** implement and test encrypted backup/restore
with a fail-closed recovery process that cannot silently revive revoked credentials.

The branch is ready for code review as a pilot foundation, not approval to host real
business data. Publication is restricted to `codex/company-knowledge-mvp`; no merge
to `main`, public deployment, visibility change or paid infrastructure is authorized.
