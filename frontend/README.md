# ClarityOps React frontend

See the [root README](../README.md) for complete setup and privacy boundaries.

- `npm ci` installs the pinned dependencies.
- `npm run dev` serves the workspace on 127.0.0.1:5173 with `/api` proxied to 8000.
- `npm run lint` and `npm run build` validate the source and production bundle.
- `npm run test:e2e` starts isolated frontend/backend servers with real document
  ingestion/retrieval and a test-only answer generator; it requires prepared local
  embeddings, backend dev dependencies and a Playwright Chromium install. It covers
  both the original demo (ports 18000/15173) and company members (18001/15174).

No Gemini key belongs in this directory or in any VITE_ variable. Workspace access
is entered at runtime and kept only in memory. Uploaded text/answers are rendered
as React text nodes. Member-mode owners can issue/revoke individual access; employees
have read/query/download controls. Server authorization enforces the same rules.
New tokens are masked by default, shown once and cleared on panel close/lock.
Late responses from a locked token cannot populate another company's workspace.
Production hosting, password accounts, MFA and SSO remain outside this increment.
