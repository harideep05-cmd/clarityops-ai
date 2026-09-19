# Baseline audit - 19 September 2026

Source: `main` at `2f67311b881b0e769a39886ca8439a97354d836c`.
Audited every tracked source/config file, lockfile, asset references, and all three
commits. GitHub returned no open issues or pull requests. No AGENTS.md exists.
Work continues on `codex/company-knowledge-mvp`; main is unchanged.

| State | Evidence |
| --- | --- |
| Already implemented | FastAPI routes `/`, `/health`, `/ask`, `/upload`, `/read-pdf`; React form; Google Gen AI SDK call to `gemini-2.5-flash`; npm lockfile; localhost CORS allowlist. |
| Partially implemented | Upload writes raw bytes; PDF extraction joins text without page metadata; React renders the `/ask` response but ignores HTTP errors. These flows are disconnected. |
| Not implemented | Document registry, chunking, embeddings, retrieval, grounding, citations, deletion, authentication, tests, backend dependency definition, environment example, useful setup documentation. |
| Broken / unverified | Backend import fails without a Gemini key. Live provider behavior cannot be checked without credentials. Frontend lint fails for unused `err`. |

## Baseline execution

- `npm ci`: pass. `npm run build`: pass (Vite 8.1.5 from existing lock).
- `npm run lint`: fails at App.jsx: unused `err`.
- Installed imports in an isolated Python 3.12 environment; no previous dependency
  versions were recorded by the repository.
- Import with no GEMINI_API_KEY: ValueError before server startup.
- With **only SDK construction mocked**, `/health` is 200, valid `/upload` is 200,
  and `/read-pdf` extracts the synthetic 12-day leave policy.
- Traversal upload `../escaped.txt` writes outside uploads and returns 200
  (tested only inside a disposable directory).
- Malformed PDF: 500. Simulated provider failure: 200 with raw exception details.
- Existing ignores protect .env variants, venv, node_modules, dist, uploads.
  No tracked secret files or Google-key/private-key signatures found. This scan
  does not prove the absence of every possible secret.

## Implementation plan, based on this code

1. Pin backend dependencies, add an environment template and explicit loading;
   make provider creation lazy so missing credentials cannot break `/health`.
2. Preserve and harden the existing endpoints. Bound requests before multipart
   parsing; validate PDFs; extract in a timed subprocess; preserve page identity.
3. Store documents, chunks and local embeddings transactionally in SQLite.
   Deduplicate by bytes; avoid overwrites; delete original and derived data together.
4. Retrieve semantic evidence locally using a small CPU embedding model. Require
   grounded structured Gemini claims and validate source IDs and verbatim quotes.
5. Connect upload, document list, question, answer, source snippets, and deletion in
   the existing React application. Use the Vite same-origin development proxy.
6. Add repeatable API, retrieval, provider-contract and browser tests. Separate
   simulated-provider tests from optional real-Gemini evaluation.
7. Record limitations honestly. This cycle is a single-company local demo with a
   shared access token; multi-tenant SaaS and a real-data pilot need further work.
