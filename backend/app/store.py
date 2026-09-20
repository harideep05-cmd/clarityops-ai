import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import numpy as np

from .config import Settings
from .errors import AppError


PUBLIC_COLUMNS = "id, filename, bytes, page_count, chunk_count, created_at, warnings, created_by"


class Store:
    """One workspace per database. No user-controlled paths or tenant selectors."""

    def __init__(self, settings: Settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        settings.data_dir.chmod(0o700)
        self.path = settings.data_dir / "knowledge.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL,
                    name_key TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL UNIQUE,
                    bytes INTEGER NOT NULL, page_count INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL, created_at TEXT NOT NULL,
                    warnings TEXT NOT NULL, original BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    page INTEGER NOT NULL, char_start INTEGER NOT NULL,
                    char_end INTEGER NOT NULL, text TEXT NOT NULL,
                    embedding BLOB NOT NULL, embedding_model TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chunks_document ON chunks(document_id);
                CREATE TABLE IF NOT EXISTS document_events (
                    id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, action TEXT NOT NULL,
                    subject_id TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)
            if "created_by" not in {r[1] for r in db.execute("PRAGMA table_info(documents)")}:
                db.execute("ALTER TABLE documents ADD COLUMN created_by TEXT")
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def public(row):
        if row is None:
            return None
        return {
            **{k: row[k] for k in ("id", "filename", "bytes", "page_count", "chunk_count", "created_at")},
            "warnings": json.loads(row["warnings"]),
            "created_by": row["created_by"],
            "status": "ready",
        }

    def list_documents(self):
        with self.connection() as db:
            return [
                self.public(r)
                for r in db.execute(f"SELECT {PUBLIC_COLUMNS} FROM documents ORDER BY created_at DESC")
            ]

    def find_duplicate(self, data: bytes):
        with self.connection() as db:
            return self.public(
                db.execute(
                    f"SELECT {PUBLIC_COLUMNS} FROM documents WHERE sha256=?",
                    (hashlib.sha256(data).hexdigest(),),
                ).fetchone()
            )

    def add_document(self, filename, data, pages, chunks, vectors, model_id, warnings, actor_id="demo-owner"):
        if len(chunks) != len(vectors) or not chunks:
            raise AppError(503, "indexing_failed", "Document indexing did not complete. Please retry.")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            digest = hashlib.sha256(data).hexdigest()
            existing = db.execute(
                f"SELECT {PUBLIC_COLUMNS} FROM documents WHERE sha256=?", (digest,)
            ).fetchone()
            if existing:
                return self.public(existing), True
            if db.execute("SELECT 1 FROM documents WHERE name_key=?", (filename.casefold(),)).fetchone():
                raise AppError(
                    409,
                    "filename_exists",
                    "A different document has this filename. Rename the new PDF or remove the old document first.",
                )
            count = db.execute("SELECT count(*) FROM documents").fetchone()[0]
            total_chunks = db.execute("SELECT count(*) FROM chunks").fetchone()[0]
            if count >= self.settings.max_documents or total_chunks + len(chunks) > self.settings.max_chunks:
                raise AppError(
                    409,
                    "workspace_full",
                    "This workspace has reached its document limit. Remove unused documents.",
                )
            doc_id = uuid.uuid4().hex
            db.execute(
                """INSERT INTO documents
                (id, filename, name_key, sha256, bytes, page_count, chunk_count, created_at, warnings, original, created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    doc_id,
                    filename,
                    filename.casefold(),
                    digest,
                    len(data),
                    len(pages),
                    len(chunks),
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(warnings),
                    data,
                    actor_id,
                ),
            )
            for i, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                vector = np.asarray(vector, dtype="<f4")
                if vector.shape != (384,) or not np.isfinite(vector).all():
                    raise AppError(503, "indexing_failed", "The embedding model returned invalid data.")
                db.execute(
                    "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)",
                    (
                        f"{doc_id}:{i}",
                        doc_id,
                        chunk["page"],
                        chunk["char_start"],
                        chunk["char_end"],
                        chunk["text"],
                        vector.tobytes(),
                        model_id,
                    ),
                )
            self._event(db, actor_id, "document.uploaded", doc_id)
            return self.public(
                db.execute(f"SELECT {PUBLIC_COLUMNS} FROM documents WHERE id=?", (doc_id,)).fetchone()
            ), False

    def all_chunks(self):
        with self.connection() as db:
            return [
                dict(r)
                for r in db.execute("""
                SELECT c.*, d.filename FROM chunks c JOIN documents d ON c.document_id=d.id
                ORDER BY c.id
            """)
            ]

    def existing_ids(self, ids):
        with self.connection() as db:
            return {r[0] for r in db.execute("SELECT id FROM documents")}.issuperset(ids)

    @staticmethod
    def _event(db, actor_id, action, doc_id):
        db.execute("INSERT INTO document_events VALUES (?,?,?,?,?)",
                   (uuid.uuid4().hex, actor_id, action, doc_id, datetime.now(timezone.utc).isoformat()))

    def events(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM document_events ORDER BY created_at DESC, rowid DESC LIMIT 100")]

    def delete(self, doc_id, actor_id="demo-owner"):
        with self.connection() as db:
            if db.execute("DELETE FROM documents WHERE id=?", (doc_id,)).rowcount == 0:
                raise AppError(404, "document_not_found", "That document was not found.")
            self._event(db, actor_id, "document.deleted", doc_id)

    def document_file(self, doc_id):
        with self.connection() as db:
            row = db.execute("SELECT filename, original FROM documents WHERE id=?", (doc_id,)).fetchone()
            if row is None:
                raise AppError(404, "document_not_found", "That document was not found.")
            return row["filename"], row["original"]
