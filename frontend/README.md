# ClarityOps React frontend

See the [root README](../README.md) for complete setup and privacy boundaries.

- `npm ci` installs the pinned dependencies.
- `npm run dev` serves the workspace on 127.0.0.1:5173 with `/api` proxied to 8000.
- `npm run lint` and `npm run build` validate the source and production bundle.
- `npm run test:e2e` starts isolated frontend/backend servers with real document
  ingestion/retrieval and a test-only answer generator; it requires prepared local
  embeddings, backend dev dependencies and a Playwright Chromium install.

No Gemini key belongs in this directory or in any VITE_ variable. Workspace access
is entered at runtime and kept only in memory. Uploaded text/answers are rendered
as React text nodes. Production hosting and identity are outside this cycle.
