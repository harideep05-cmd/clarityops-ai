# MVP architecture decisions

## Extend the recovered app

React/Vite and FastAPI remain. The five original API routes are retained. The existing
Google Gen AI SDK and Gemini 2.5 Flash setting remain. Generic `/ask` behavior is
replaced because it cannot answer company questions reliably without document evidence.
PyPDF2 is replaced by its maintained successor pypdf; page extraction remains the core
operation, now behind validation and a subprocess boundary.

## Ingestion and storage

Requests authenticate before their bounded body is passed to multipart parsing.
The app checks filename, MIME, bytes, signature, encryption, page/text limits and
extraction errors. PDF parsing runs in a separate Python process, killed after 20s;
Linux also applies a 512 MiB address-space limit and 15s CPU limit. Windows has the
wall-clock/byte/page/text limits; its memory limit has not been implemented.

Normalize Unicode and line whitespace; retain each physical page. A chunk carries
page, normalized character start/end and text. Page-local windows are at most 1,000
characters with 180-character overlap, ending at a sentence/newline where practical.
For ordinary English this is roughly 250 tokens, below BGE's 512-token limit. The
actual tokenizer rejects text over 480 tokens rather than silently truncating it.
The overlap protects boundary clauses; the tradeoff is duplicate evidence and an
inability to combine context automatically across page boundaries.

SQLite stores original PDF bytes as a BLOB and chunk/vector rows in the same
transaction. This avoids using user filenames as paths, partial index/file commits,
and orphaned files on deletion. UUID document IDs and per-document ordinal chunk IDs
are independent of display names. SHA-256 deduplicates identical bytes. Different
content with the same normalized, casefolded filename returns 409, never an overwrite.

The connection uses foreign keys, secure deletion, short transactions and SQLite's
default DELETE journal, not a retained WAL. Original/derived data disappear together
from the active database. Filesystem/SSD/backups/provider retention are separate.
Metadata listing does not read original PDF BLOBs. Storage quotas bound the corpus;
there is no distributed ingestion queue in this cycle.

## Local semantic search

Use [FastEmbed](https://github.com/qdrant/fastembed) with the quantized
[BGE-small English model](https://huggingface.co/qdrant/bge-small-en-v1.5-onnx-q).
Revision `52398278842ec682c6f32300af41344b1c0b0bb2` is pinned. Setup downloads explicit
files over HTTPS and records SHA-256 checksums; runtime verifies them and only loads
local files. Changing the model identity requires reindexing, not mixing vectors.

Embeddings are unit-normalized 384-dimensional float32 vectors. Search computes an
exact cosine scan over at most 5,000 chunks. This is inexpensive and inspectable at
our demo scale. No remote embedding call sends company text out of the host.

Return at most five chunks, with cosine >= 0.55 and within 0.10 of the strongest
match; remove near-identical overlapping windows. Those are conservative starting
heuristics, checked on the synthetic sample, not calibrated confidence probabilities.
Five topic queries ranked their expected page first. A related-but-unsupported topic
such as parental leave can still retrieve the casual-leave page: **retrieval relevance
alone is not an answerability test**. Gemini must abstain when the specific answer is
missing; live evaluation of this behavior remains required.

## Generation and evidence

Use the [Google Gen AI SDK's structured responses](https://googleapis.github.io/python-genai/)
with a JSON schema: supported flag and factual claims. Each claim must identify a
retrieved source ID and quote supporting text verbatim. The system prompt treats
questions/documents as untrusted data, forbids external knowledge as company policy,
and requires refusal for insufficient, conflicting or partial evidence. No tools,
URL fetching, autonomous actions or generic-chat fallback are enabled.

The server verifies known source IDs, nonblank exact quotations, and that numeric
values in claims occur in their quotations. It attaches document/page metadata from
its own index. A failed attribution check returns the standard insufficient-evidence
response. Empty/invalid JSON and provider errors become controlled 502 responses.
Provider requests have a 30-second SDK timeout and one attempt; keys are initialized
lazily. No retrieval result means no provider call.

These checks prove quote provenance, not that a natural-language claim logically
follows from a quote. Numeric checks also do not cover every representation of a
number. Real-provider evaluation, conflicting-version cases and prompt-injection
cases are mandatory before making reliability claims to paying customers.
