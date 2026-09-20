"""Small pilot identity registry. Opaque credentials are stored only as SHA-256 hashes.

The tokens contain 256 bits of randomness; these are not user-chosen passwords.
Workspace/role come exclusively from this registry, never request parameters.
"""

import hashlib
import secrets
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .errors import AppError


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_name(value):
    value = unicodedata.normalize("NFKC", value).strip()
    if not 1 <= len(value) <= 80 or any(unicodedata.category(c).startswith("C") for c in value):
        raise AppError(422, "invalid_name", "Use a name of 1–80 characters without control characters.")
    return value


def new_token():
    return "clo_" + secrets.token_urlsafe(32)


@dataclass(frozen=True)
class Principal:
    workspace_id: str
    workspace_name: str
    member_id: str
    name: str
    role: str

    @property
    def can_manage(self):
        return self.role == "owner"


DEMO_PRINCIPAL = Principal("legacy", "Local demo", "demo-owner", "Demo owner", "owner")
MEMBER_COLUMNS = "id, name, role, created_at, expires_at, revoked_at"


class IdentityRegistry:
    def __init__(self, settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        settings.data_dir.chmod(0o700)
        self.path = settings.data_dir / "identity.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS members (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    name TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('owner','employee')),
                    token_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL, revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS members_workspace ON members(workspace_id);
                CREATE TABLE IF NOT EXISTS identity_events (
                    id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    actor_id TEXT NOT NULL, action TEXT NOT NULL, subject_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
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
    def _event(db, workspace, actor, action, subject):
        db.execute(
            "INSERT INTO identity_events VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex, workspace, actor, action, subject, now()),
        )

    def authenticate(self, token):
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            return None
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.connection() as db:
            row = db.execute(
                """
                SELECT m.*, w.name AS workspace_name FROM members m
                JOIN workspaces w ON m.workspace_id=w.id
                WHERE m.token_hash=? AND m.revoked_at IS NULL AND m.expires_at>?
            """,
                (digest, now()),
            ).fetchone()
        if row is None:
            return None
        return Principal(row["workspace_id"], row["workspace_name"], row["id"], row["name"], row["role"])

    @staticmethod
    def _require_active(db, actor, owner=False):
        row = db.execute(
            """
            SELECT role FROM members WHERE id=? AND workspace_id=?
            AND revoked_at IS NULL AND expires_at>?
        """,
            (actor.member_id, actor.workspace_id, now()),
        ).fetchone()
        if row is None or row["role"] != actor.role or (owner and row["role"] != "owner"):
            raise AppError(403, "access_revoked", "Your access changed. Unlock the workspace again.")

    def require_active(self, actor, owner=False):
        with self.connection() as db:
            self._require_active(db, actor, owner)

    def _insert_member(self, db, workspace, name, role, days):
        name = clean_name(name)
        if role not in {"owner", "employee"} or type(days) is not int or not 1 <= days <= 30:
            raise AppError(422, "invalid_membership", "Choose owner or employee and 1–30 days of access.")
        if (
            db.execute("SELECT count(*) FROM members WHERE workspace_id=?", (workspace,)).fetchone()[0]
            >= self.settings.max_members
        ):
            raise AppError(409, "member_limit", "This pilot workspace has reached its member record limit.")
        token, member_id = new_token(), uuid.uuid4().hex
        expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")
        db.execute(
            "INSERT INTO members VALUES (?,?,?,?,?,?,?,NULL)",
            (member_id, workspace, name, role, hashlib.sha256(token.encode()).hexdigest(), now(), expires),
        )
        member = dict(db.execute(f"SELECT {MEMBER_COLUMNS} FROM members WHERE id=?", (member_id,)).fetchone())
        return member, token

    def create_workspace(self, name, owner_name, deliver=None):
        """Operator-only bootstrap. A failed credential-file delivery rolls back creation."""
        name = clean_name(name)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM workspaces").fetchone()[0] >= self.settings.max_workspaces:
                raise AppError(
                    409, "workspace_limit", "This pilot installation has reached its workspace limit."
                )
            workspace = {"id": uuid.uuid4().hex, "name": name}
            db.execute("INSERT INTO workspaces VALUES (?,?,?)", (workspace["id"], name, now()))
            member, token = self._insert_member(db, workspace["id"], owner_name, "owner", 30)
            self._event(db, workspace["id"], "operator", "workspace.created", member["id"])
            result = {"workspace": workspace, "member": member, "access_token": token}
            if deliver:
                deliver(result)
            return result

    def issue_owner(self, workspace_id, name, deliver=None):
        """Local operator recovery; never exposed as an unauthenticated HTTP endpoint."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id, name FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
            if row is None:
                raise AppError(404, "workspace_not_found", "That workspace was not found.")
            member, token = self._insert_member(db, workspace_id, name, "owner", 30)
            self._event(db, workspace_id, "operator", "owner.recovered", member["id"])
            result = {"workspace": dict(row), "member": member, "access_token": token}
            if deliver:
                deliver(result)
            return result

    def list_members(self, actor):
        with self.connection() as db:
            self._require_active(db, actor, owner=True)
            return [
                dict(r)
                for r in db.execute(
                    f"SELECT {MEMBER_COLUMNS} FROM members WHERE workspace_id=? ORDER BY created_at, id",
                    (actor.workspace_id,),
                )
            ]

    def add_member(self, actor, name, role="employee", days=30):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require_active(db, actor, owner=True)
            member, token = self._insert_member(db, actor.workspace_id, name, role, days)
            self._event(db, actor.workspace_id, actor.member_id, "member.created", member["id"])
            return {"member": member, "access_token": token}

    def revoke(self, actor, member_id):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._require_active(db, actor, owner=True)
            if actor.member_id == member_id:
                raise AppError(
                    409, "cannot_revoke_self", "Create another owner before replacing your access."
                )
            row = db.execute(
                "SELECT revoked_at FROM members WHERE id=? AND workspace_id=?",
                (member_id, actor.workspace_id),
            ).fetchone()
            if row is None:
                raise AppError(404, "member_not_found", "That member was not found.")
            if row["revoked_at"] is None:
                db.execute(
                    "UPDATE members SET revoked_at=? WHERE id=? AND workspace_id=?",
                    (now(), member_id, actor.workspace_id),
                )
                self._event(db, actor.workspace_id, actor.member_id, "member.revoked", member_id)

    def events(self, actor):
        with self.connection() as db:
            self._require_active(db, actor, owner=True)
            return [
                dict(r)
                for r in db.execute(
                    """
                SELECT id, actor_id, action, subject_id, created_at FROM identity_events
                WHERE workspace_id=? ORDER BY created_at DESC, rowid DESC LIMIT 100
            """,
                    (actor.workspace_id,),
                )
            ]
