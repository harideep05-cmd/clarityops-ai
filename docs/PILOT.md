# Private-pilot foundation and operator runbook

Updated 20 September 2026. This run added opt-in company isolation, member access,
owner controls and management audit events. It did not deploy a service or authorize
confidential customer data. Use synthetic material until the acceptance gates below
are closed.

## Access and storage model

| Mode | Identity | Knowledge storage | Intended use |
| --- | --- | --- | --- |
| `demo` (default) | Existing shared environment token; everyone is an owner | Existing `data/knowledge.sqlite3` | Existing local demonstration |
| `members` | Registry-backed person, company and owner/employee role | `data/tenants/<generated-workspace-id>/knowledge.sqlite3` | Testing the pilot foundation |

`data/identity.sqlite3` holds companies, memberships, token hashes and membership
events. Tokens contain 256 random bits, are returned once, expire within 30 days and
can be revoked. Hashing protects stored high-entropy credentials; this is not password
storage, MFA or an identity provider. Token possession grants that member's access.
No query parameter, document ID, header, filename or request body chooses a company.
Every scoped store is selected from the authenticated registry record.

The public embedding model is shared and immutable after loading. Original PDFs,
chunks, vectors, deduplication, filenames and document audit events live in separate
company databases. The single service process still has OS access to all of them;
this is application-level isolation, not separate machines/security principals.

| Capability | Owner | Employee |
| --- | --- | --- |
| List own company's documents, ask, inspect citations, download originals | Yes | Yes |
| Upload/index, extract an arbitrary PDF, delete documents | Yes | No |
| Issue/revoke company member access, view management audit events | Yes | No |
| Create another company or recover an owner without a valid token | Local operator only | No |

Employees are denied writes before request-body parsing. Owners cannot revoke their
own token through HTTP. Create a replacement owner, unlock with that token, then
revoke the old one. Access is rechecked after long indexing/generation operations;
already delivered responses/downloads cannot be recalled by revocation.

## Windows setup without changing the existing demo collection

Complete the normal README setup, then use a terminal in `backend`. Keep your
existing Gemini key private and unchanged. Create a synthetic workspace:

```powershell
.\.venv\Scripts\python.exe scripts\pilot_admin.py create-workspace --name "Synthetic Company" --owner "Owner" --credential-file .\data\owner-access.json
notepad .env
```

Set `CLARITYOPS_AUTH_MODE=members` and leave `CLARITYOPS_DEPLOYMENT=local`. Restart
the backend with the documented loopback Uvicorn command. Read the owner credential
locally with `notepad .\data\owner-access.json`; use its `access_token` in the
unlock form. Never paste this file, its token or `.env` into chat, issues or logs.
The helper refuses overwrites, saves with Unix mode 0600 and prints only the company
ID and safe setup guidance. On Windows, restrict the directory ACL to the operator
and service account; Unix permission bits are not Windows ACL enforcement.

If `CLARITYOPS_DATA_DIR` is customized, put the credential file inside that actual
directory. Custom directories inside the repository need matching ignore rules.
The bootstrap secret remains in that file until you deliberately remove it after
saving it securely; database storage contains only its hash.

An owner can now upload approved material and issue **30-day access** from the React
member panel. The UI defaults to Employee. Share the displayed token through a
private channel outside ClarityOps; there is no email/invitation sender. Closing the
panel or locking the app clears the displayed secret. Revoke access from the same
panel. API-issued tokens can specify 1–30 days.

Repeat `create-workspace` with a different credential filename to provision another
company. A second browser profile/private window makes company-isolation testing
easy. There are no client-side company switch controls: another token selects another
membership. The same person needing two companies currently needs two credentials.

### Legacy data and rollback

Existing shared documents are neither moved nor deleted. New company collections
start empty. Deliberately re-upload approved PDFs into the correct company. Do not
copy a shared database into multiple companies or assume old documents have owners.
The document schema upgrade only adds nullable uploader metadata and an audit table;
the migration test verifies existing PDF bytes, chunk/vector bytes, page metadata,
deduplication and retrieval remain intact across repeat startup.

Setting `CLARITYOPS_AUTH_MODE=demo` restores the old local collection and its existing
shared token. It does not expose the separate member collections. Never use demo mode
for hosted access; `CLARITYOPS_DEPLOYMENT=private` rejects that combination at startup.

### Lost/expired owner access

An authorized local operator can create replacement owner access without seeing any
existing credential. Substitute the workspace ID from the bootstrap file/status:

```powershell
.\.venv\Scripts\python.exe scripts\pilot_admin.py recover-owner --workspace WORKSPACE_ID --owner "Recovery owner" --credential-file .\data\recovery-owner.json
```

This creates a new audited owner membership; it does not silently revoke other owners.
Review/revoke superseded access afterward. No recovery endpoint exists over HTTP.

## Governance and retention

Only owners publish PDFs to their company collection. Uploaded documents become
searchable immediately after successful indexing: no separate draft/approval/version
workflow exists. Metadata includes document ID, filename, timestamps, physical pages,
warnings and uploader member ID (unknown for legacy documents).

Document upload/delete audit events commit in the same transaction as the data change.
Member creation/revocation/recovery events commit in the identity registry transaction.
`GET /audit` returns the latest 100 combined events to an owner in that company.
Events contain actor/subject IDs, action and time, not policy text, questions, tokens
or filenames. These local tables are not tamper-evident logs or a complete access log.
Queries/downloads, failed authentication and denied actions do not receive durable
audit events in this increment.

Deletion removes the company's active PDF, text and vectors together. Minimal audit
records remain; revoked member names/IDs remain. No automatic retention, legal hold,
member-data erasure or company deletion feature exists. Define retention and backup
expiry with the pilot owner before real data. Downloaded copies and Gemini processing
are separate from local deletion.

## Private hosting preparation — not a deployment

The configuration supports `CLARITYOPS_DEPLOYMENT=private`, which requires member
authentication and exact HTTPS frontend origins. It checks configuration, not actual
TLS/network reachability. Before exposing any pilot endpoint:

1. Select an approved private access boundary (VPN/private network/access gateway).
   Terminate TLS at a managed reverse proxy and keep Uvicorn on loopback with one
   worker. Serve the built React assets; proxy `/api/*` to FastAPI with `/api` removed.
   Do not expose Vite's development server or an unprotected backend port.
2. Use an unprivileged service identity and encrypted persistent storage. Keep
   `GEMINI_API_KEY` in the host's secret configuration, never frontend build variables.
   Set an absolute data directory and its OS ACLs before placing documents there.
3. Set `CLARITYOPS_AUTH_MODE=members`, `CLARITYOPS_DEPLOYMENT=private`, and
   `CLARITYOPS_CORS_ORIGINS` to the exact approved HTTPS UI origin. Reject wildcard,
   credential-bearing, path-containing or unencrypted private origins.
4. Apply proxy request/rate limits and service CPU/memory/disk limits. The app has
   four shared in-flight slots and 60 authenticated requests/minute per company;
   these are not distributed limits or a guarantee against a noisy neighbor.
5. Keep access/body/provider debug logging off. Monitor liveness separately from
   configuration indicators, plus aggregate failures, disk space, backups and provider
   quota. No monitoring agent, alert routing or service supervision is installed here.

Limits: 20 workspaces/installation, 100 member records/workspace including revoked
records, 50 documents and 5,000 chunks/workspace. There is no automatic record purging
or unlimited scaling. Assess capacity before hitting these limits.

## Backup and restore procedure

A **stopped-server copy/restore of the entire data directory** was tested using
synthetic data, real SQLite and membership credentials. This is a procedure check,
not a managed or encrypted backup product.

1. Stop all backend processes and operator CLI writes. Copy the complete data root
   to an encrypted, access-controlled backup location. Identity plus every tenant
   database must come from the same stopped state; copying only a document database
   loses its membership mapping. Model files can instead be prepared again.
2. Store secret environment configuration separately in the approved secret store.
   Bootstrap credential files under the data root are also secrets; protect them.
3. Restore into a **new empty directory** while the service remains inaccessible.
   Reapply OS permissions, point `CLARITYOPS_DATA_DIR` there, and verify membership,
   owner/employee permissions, PDF downloads and cross-company denial on loopback.
4. An older backup can revive credentials that were revoked after the snapshot.
   Reconcile revocations and replace affected credentials before restoring access.
   This reconciliation is not automated; do not reopen a restored pilot until it is
   complete. Retain an incident record without raw tokens.
5. Schedule and test encrypted backups, restoration, credential reconciliation and
   expiry before real customer use. Agree recovery objectives and backup retention.

## Acceptance gates before a real business

- Run a deliberate, quota-aware local Gemini check of this revision and a broader
  approved evaluation set: supported policies, near matches, missing benefits,
  conflicting versions, prompt injection and source correctness. The owner reported
  seven live passes on `1c06282`; no live calls were made in this continuation.
- Validate the new member workflow on Windows. Earlier Windows MVP verification is
  owner-reported; this increment was executed on Linux/Chromium.
- Complete private TLS/network isolation, service limits, encrypted storage, backup
  automation/restore reconciliation, monitoring and an operator incident procedure.
- Agree permitted data, Gemini processing/retention, access ownership and deletion
  obligations. Do not treat a public source repository as a place for pilot data.

Design references: [OWASP tenant isolation guidance](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html)
and [authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
These informed the server-derived scope and authorization-at-each-request design;
they do not certify this implementation.
