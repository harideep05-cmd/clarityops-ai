# Security and privacy review

Scope: local single-company MVP, reviewed 19 September 2026. This is not a penetration
test or compliance certification. No customer documents were used.

| Finding in recovered app | Change | Residual boundary |
| --- | --- | --- |
| Raw filenames become filesystem paths | Reject unsafe names; originals use UUID-addressed SQLite BLOBs | Multipart may strip Windows path prefixes; resulting display name is never a storage path. |
| Arbitrary/unbounded upload | PDF/MIME/header checks; pre-parser request cap; file, page, text and workspace quotas | PDFs remain untrusted; no malware/content-disarm scanner. Downloads are attachments. |
| Unbounded parsing | Timed subprocess with Linux memory/CPU caps; remove application secrets from its inherited environment | This is not an OS sandbox. Windows process memory is not separately capped; complex layouts may extract poorly. |
| Anyone can read/upload/ask | Constant-time shared access token check before body parsing | All token holders have equal read/write/delete powers; no accounts or RBAC. |
| No company isolation model | Exactly one workspace/data directory per app process; no client-selected tenant | Multi-company sharing of one process/database is prohibited; separate-process tests are not proof of multi-tenant SaaS isolation. |
| Exception text sent to users | Structured error codes + request IDs; type-only diagnostics; catch unexpected failures before server traceback logging | Operators must avoid enabling HTTP/body debug logging. |
| Import requires Gemini key | Lazy provider initialization, controlled 503 on missing key | Validity, quota, latency and model availability require live credentials/testing. |
| No citation/grounding validation | Evidence-only prompt, structured claims, quote/source/numeric validation | Not a formal entailment check; adversarial model behavior remains possible. |
| No deletion or atomic indexing | SQLite transactions, cascade deletion and secure_delete | Does not erase downloaded copies, backups, cached browser results or provider retention. |
| Wide method/header CORS | Explicit origins, methods and headers; unexpected origins rejected | CORS is not authentication; remote use also requires TLS and a private access layer. |
| Secrets/data could enter Git | .env/data/uploads/DB/models/build/cache ignores; diff/history signature scan | Ignore rules do not protect force-added files or custom directories; inspect every commit. |

## Data handling

- Ingestion, text, embeddings, filenames and original PDFs remain in the backend's
  local data directory. Directory/database permissions restrict Unix access (0700/0600).
  Startup also hardens an existing data directory created by model setup.
  This is not encryption. Use OS disk encryption and controlled service accounts for
  any future private-data environment; Windows ACLs need explicit review.
- Gemini receives questions, selected snippets, display filenames and page numbers.
  This is shown in the UI. Review the provider's current account-specific processing,
  retention and training terms with the pilot owner before using confidential data.
- ClarityOps stores no conversations and logs no document/question text, API keys,
  tokens or provider exception bodies. Browser token lives only in component memory.
- Public liveness returns no document/configuration information. Status/list/download/
  extraction/ask/delete are token protected. OpenAPI UI routes are disabled.
- App limits: four concurrent private requests, 60 authenticated requests/minute per
  process, 30s total request-body deadline, 16 KiB question body and 10 MiB + 64 KiB
  upload envelope. These are local protective caps, not a distributed rate limiter.

## Before a private pilot

1. Run live-provider acceptance tests plus a customer-approved, non-sensitive evaluation
   set, including missing policies, conflicting versions, near-match questions and
   malicious document instructions. Track false answers and abstentions separately.
2. Implement distinct owner/employee identities, scoped permissions and document access
   where required. Choose explicit tenant isolation before supporting a second company.
3. Deploy privately behind TLS/authentication with process resource limits, encrypted
   persistent storage, backup/restore verification, dependency updates and health monitoring.
4. Agree on allowed data, consent to Gemini processing, retention/deletion expectations,
   and a named human owner for high-impact policy decisions.

There is no deployment, data-retention contract, managed backup, or production identity
service in this cycle. The current safe demonstration uses the synthetic handbook.
