# Security and privacy review

Scope: local MVP and opt-in pilot workspaces, reviewed 20 September 2026. This is not a penetration
test or compliance certification. No customer documents were used.

| Finding in recovered app | Change | Residual boundary |
| --- | --- | --- |
| Raw filenames become filesystem paths | Reject unsafe names; originals use UUID-addressed SQLite BLOBs | Multipart may strip Windows path prefixes; resulting display name is never a storage path. |
| Arbitrary/unbounded upload | PDF/MIME/header checks; pre-parser request cap; file, page, text and workspace quotas | PDFs remain untrusted; no malware/content-disarm scanner. Downloads are attachments. |
| Unbounded parsing | Timed subprocess with Linux memory/CPU caps; remove application secrets from its inherited environment | This is not an OS sandbox. Windows process memory is not separately capped; complex layouts may extract poorly. |
| Anyone can read/upload/ask | Demo shared-token check; opt-in member credentials with owner/employee authorization before body parsing | Member tokens are bearer credentials, not passwords/MFA/SSO. Protect delivery; demo access remains owner-equivalent. |
| No company isolation model | Registry-derived company context and separate company databases, including retrieval/download/delete; cross-company and concurrent real-retrieval tests | Shared process, OS identity, embedding model and provider quota; not OS-level or distributed isolation. |
| Exception text sent to users | Structured error codes + request IDs; type-only diagnostics; catch unexpected failures before server traceback logging | Operators must avoid enabling HTTP/body debug logging. |
| Import requires Gemini key | Lazy provider initialization, controlled 503 on missing key | Validity, quota, latency and model availability require live credentials/testing. |
| No citation/grounding validation | Evidence-only prompt, structured claims, quote/source/numeric validation | Not a formal entailment check; adversarial model behavior remains possible. |
| No deletion or atomic indexing | SQLite transactions, cascade deletion and secure_delete | Does not erase downloaded copies, backups, cached browser results or provider retention. |
| Wide method/header CORS | Explicit origins, methods and headers; unexpected origins rejected | CORS is not authentication; remote use also requires TLS and a private access layer. |
| Secrets/data could enter Git | .env/data/uploads/DB/models/build/cache ignores; diff/history signature scan | Ignore rules do not protect force-added files or custom directories; inspect every commit. |
| No individual revocation/expiry | Hash-only member credential storage, up to 30-day expiry, owner revocation, operator recovery | No automatic renewal; restoring an old backup can resurrect revoked credentials unless reconciled before access resumes. |
| No management audit | Transactional document and membership events with actor IDs; owner-only scoped read API | Not tamper-evident; no complete read/authentication audit, retention automation or SIEM. |
| Hosted demo misconfiguration | Private deployment mode rejects shared-token auth and non-HTTPS CORS origins | This validates config only; operator must actually implement private TLS, ACLs and service limits. |

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
  Locking clears the workspace; late responses/errors from a different access token
  cannot update the active UI. A browser regression covers switching companies while
  an earlier answer is still in flight.
- Public liveness returns no document/configuration information. Status/list/download/
  extraction/ask/delete are token protected. OpenAPI UI routes are disabled.
- App limits: four concurrent private requests shared across companies, 60 authenticated requests/minute per
  company, 30s total request-body deadline, 16 KiB question body and 10 MiB + 64 KiB
  upload envelope. These are local protective caps, not a distributed rate limiter.

## Before a private pilot

1. Run live-provider acceptance tests plus a customer-approved, non-sensitive evaluation
   set, including missing policies, conflicting versions, near-match questions and
   malicious document instructions. Track false answers and abstentions separately.
2. Exercise the new owner/employee member mode with the pilot owner, review credential
   delivery/recovery and company boundaries, and decide whether finer document ACLs or
   stronger identity verification are required. Validate the new workflow on Windows.
3. Deploy privately behind TLS/authentication with process resource limits, encrypted
   persistent storage, backup/restore verification, dependency updates and health monitoring.
4. Agree on allowed data, consent to Gemini processing, retention/deletion expectations,
   and a named human owner for high-impact policy decisions.

There is no deployment, data-retention contract, managed backup, or production identity
service in this cycle. The current safe demonstration uses the synthetic handbook.
