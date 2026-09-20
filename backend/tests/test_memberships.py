import asyncio
import hashlib
import json
import sqlite3
from dataclasses import replace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.embeddings import retrieve
from app.identity import IdentityRegistry
from app.main import create_app
from app.security import RequestGuard
from app.store import Store
from app.workspaces import WorkspaceStores
from conftest import EvidenceAnswerer, FakeEmbeddings, TEST_TOKEN, pdf_bytes
from test_ingestion import upload


@pytest.fixture
def companies(settings):
    settings = replace(settings, auth_mode="members")
    registry = IdentityRegistry(settings)
    a = registry.create_workspace("Synthetic Alpha", "Alpha owner")
    b = registry.create_workspace("Synthetic Beta", "Beta owner")
    actor = registry.authenticate(a["access_token"])
    employee = registry.add_member(actor, "Alpha employee")
    return settings, registry, a, b, employee


def headers(person):
    return {"X-ClarityOps-Token": person["access_token"]}


def test_two_companies_never_share_documents_or_evidence(companies):
    settings, registry, a, b, employee = companies
    answerer = EvidenceAnswerer()
    with TestClient(create_app(settings, FakeEmbeddings(), answerer)) as c:
        c.headers.update(headers(a))
        original = pdf_bytes()
        doc = upload(c, original).json()["document"]
        assert doc["created_by"] == a["member"]["id"]
        c.headers.update(headers(b))
        assert c.get("/documents").json()["documents"] == []
        for path in [f"/documents/{doc['id']}/file", f"/documents/{doc['id']}"]:
            response = c.get(path) if path.endswith("file") else c.delete(path)
            assert response.status_code == 404
        with patch.object(answerer, "answer", wraps=answerer.answer) as provider:
            result = c.post("/ask", json={"prompt": "How many casual leave days?"})
            assert result.json()["status"] == "insufficient_evidence"
            provider.assert_not_called()
        # Duplicate hashes and filenames are scoped to a company, not a global registry.
        second = upload(c, original)
        assert second.status_code == 201 and second.json()["document"]["id"] != doc["id"]
        c.headers.update(headers(employee))
        c.headers["X-Workspace-ID"] = b["workspace"]["id"]
        c.headers["X-ClarityOps-Role"] = "owner"
        result = c.post("/ask", json={"prompt": "How many casual leave days?"}).json()
        assert result["status"] == "answered"
        assert result["sources"][0]["document_id"] == doc["id"]
        assert result["sources"][0]["page"] == 1
        assert c.get(f"/documents/{doc['id']}/file").content == original
        assert c.get("/status").json()["workspace"]["id"] == a["workspace"]["id"]
        # A differently scoped company can never delete Alpha's source.
        c.headers.update(headers(b))
        assert c.delete(f"/documents/{doc['id']}").status_code == 404


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/upload"),
        ("POST", "/read-pdf"),
        ("DELETE", "/documents/unknown"),
        ("GET", "/members"),
        ("POST", "/members"),
        ("DELETE", "/members/unknown"),
        ("GET", "/audit"),
    ],
)
def test_employee_denied_before_body_read(companies, method, path):
    settings, registry, _, _, employee = companies
    guard = RequestGuard(None, settings, registry.authenticate)
    sent = []

    async def receive():
        raise AssertionError("Unauthorized body was read")

    async def send(message):
        sent.append(message)

    asyncio.run(
        guard(
            {
                "type": "http",
                "method": method,
                "path": path,
                "headers": [(b"x-clarityops-token", employee["access_token"].encode())],
            },
            receive,
            send,
        )
    )
    assert sent[0]["status"] == 403


def test_member_tokens_are_hashed_expiring_and_revocable(companies):
    settings, registry, a, b, employee = companies
    with registry.connection() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM members")]
        assert employee["access_token"] not in json.dumps(rows)
        assert any(
            r["token_hash"] == hashlib.sha256(employee["access_token"].encode()).hexdigest() for r in rows
        )
    with TestClient(create_app(settings, FakeEmbeddings())) as c:
        assert c.get("/documents", headers={"X-ClarityOps-Token": TEST_TOKEN}).status_code == 401
        assert c.get("/members", headers=headers(b)).json()["members"][0]["id"] == b["member"]["id"]
        assert c.delete(f"/members/{employee['member']['id']}", headers=headers(b)).status_code == 404
        assert c.delete(f"/members/{a['member']['id']}", headers=headers(a)).status_code == 409
        member_list = c.get("/members", headers=headers(a))
        assert "token" not in member_list.text
        assert c.delete(f"/members/{employee['member']['id']}", headers=headers(a)).status_code == 204
        assert c.get("/documents", headers=headers(employee)).status_code == 401
        with registry.connection() as db:
            db.execute(
                "UPDATE members SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (b["member"]["id"],)
            )
        assert c.get("/documents", headers=headers(b)).status_code == 401


def test_owner_can_issue_scoped_access_and_audit_changes(companies):
    settings, _, a, b, _ = companies
    with TestClient(create_app(settings, FakeEmbeddings()), headers=headers(a)) as c:
        issued = c.post("/members", json={"name": "New teammate", "role": "employee", "expires_in_days": 7})
        assert issued.status_code == 201 and issued.headers["cache-control"] == "no-store"
        token = issued.json()["access_token"]
        assert c.get("/status", headers={"X-ClarityOps-Token": token}).json()["member"]["role"] == "employee"
        assert (
            c.post("/members", json={"name": "Attacker", "workspace_id": b["workspace"]["id"]}).status_code
            == 422
        )
        assert c.post("/members", json={"name": "Attacker", "role": "superadmin"}).status_code == 422
        assert c.post("/members", json={"name": "Attacker", "expires_in_days": True}).status_code == 422
        doc = upload(c, pdf_bytes()).json()["document"]
        assert upload(c, pdf_bytes()).status_code == 200
        assert c.delete(f"/documents/{doc['id']}").status_code == 204
        events = c.get("/audit").json()["events"]
        assert [e["action"] for e in events].count("document.uploaded") == 1
        assert any(e["action"] == "document.deleted" and e["subject_id"] == doc["id"] for e in events)
        assert all(e["actor_id"] in {"operator", a["member"]["id"]} for e in events)
        assert "Employees receive" not in json.dumps(events) and token not in json.dumps(events)
        other_events = c.get("/audit", headers=headers(b)).json()["events"]
        assert all(e["subject_id"] != doc["id"] for e in other_events)


def test_workspace_budgets_are_independent(companies):
    settings, _, a, b, _ = companies
    with TestClient(create_app(replace(settings, requests_per_minute=1))) as c:
        assert c.get("/documents", headers=headers(a)).status_code == 200
        assert c.get("/documents", headers=headers(a)).status_code == 429
        assert c.get("/documents", headers=headers(b)).status_code == 200


def test_revocation_during_generation_withholds_answer(companies):
    settings, registry, a, _, employee = companies
    answerer = EvidenceAnswerer()
    with TestClient(create_app(settings, FakeEmbeddings(), answerer), headers=headers(a)) as c:
        upload(c, pdf_bytes())
        original = answerer.answer

        def revoke(question, evidence):
            result = original(question, evidence)
            registry.revoke(registry.authenticate(a["access_token"]), employee["member"]["id"])
            return result

        with patch.object(answerer, "answer", side_effect=revoke):
            result = c.post("/ask", json={"prompt": "casual leave?"}, headers=headers(employee))
        assert result.status_code == 403 and "Employees receive" not in result.text


def test_registry_persists_and_never_falls_back_to_demo(companies):
    settings, _, a, _, _ = companies
    with TestClient(create_app(settings, FakeEmbeddings()), headers=headers(a)) as c:
        doc = upload(c, pdf_bytes()).json()["document"]
    with TestClient(create_app(settings, FakeEmbeddings()), headers=headers(a)) as c:
        assert c.get("/documents").json()["documents"][0]["id"] == doc["id"]
        assert c.get("/documents", headers={"X-ClarityOps-Token": TEST_TOKEN}).status_code == 401
        with patch.object(
            c.app.state.identity, "authenticate", side_effect=RuntimeError("private registry error")
        ):
            response = c.get("/documents")
        assert response.status_code == 503 and "private registry error" not in response.text


def test_old_database_migration_preserves_originals_and_index(settings):
    # Model the pre-membership schema, including existing searchable chunks/vectors.
    settings.data_dir.mkdir()
    data = pdf_bytes()
    text = "Employees receive 12 casual leave days per calendar year."
    embeddings = FakeEmbeddings()
    vector = embeddings.embed([text])[0].tobytes()
    chunk = ("old:0", "old", 1, 0, len(text), text, vector, embeddings.model_id)
    with sqlite3.connect(settings.data_dir / "knowledge.sqlite3") as db:
        db.execute("""CREATE TABLE documents (id TEXT PRIMARY KEY, filename TEXT NOT NULL,
                   name_key TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL UNIQUE, bytes INTEGER NOT NULL,
                   page_count INTEGER NOT NULL, chunk_count INTEGER NOT NULL, created_at TEXT NOT NULL,
                   warnings TEXT NOT NULL, original BLOB NOT NULL)""")
        db.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("old", "Old.pdf", "old.pdf", hashlib.sha256(data).hexdigest(),
             len(data), 1, 1, "2026-09-19", "[]", data),
        )
        db.execute("""CREATE TABLE chunks (id TEXT PRIMARY KEY,
                   document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                   page INTEGER NOT NULL, char_start INTEGER NOT NULL, char_end INTEGER NOT NULL,
                   text TEXT NOT NULL, embedding BLOB NOT NULL, embedding_model TEXT NOT NULL)""")
        db.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?)", chunk)
    for _ in range(2):  # The upgrade is additive and remains safe on repeat startup.
        store = Store(settings)
        assert store.document_file("old") == ("Old.pdf", data)
        document = store.list_documents()[0]
        assert document["id"] == "old" and document["created_by"] is None
        assert document["chunk_count"] == 1
        assert store.find_duplicate(data)["id"] == "old"
        with store.connection() as db:
            assert tuple(db.execute("SELECT * FROM chunks").fetchone()) == chunk
        evidence = retrieve("How much casual leave?", store, embeddings, settings)
        assert len(evidence) == 1
        assert evidence[0]["id"] == "old:0" and evidence[0]["document_id"] == "old"
        assert evidence[0]["page"] == 1 and evidence[0]["text"] == text


@pytest.mark.parametrize("bad_id", ["../legacy", "", "other", "a" * 31, "a" * 33])
def test_storage_rejects_untrusted_workspace_ids(settings, bad_id):
    from app.errors import AppError

    with pytest.raises(AppError):
        WorkspaceStores(settings).get(bad_id)


def test_failed_credential_delivery_rolls_back_bootstrap(settings):
    registry = IdentityRegistry(settings)

    def fail(result):
        raise OSError("synthetic write failure")

    with pytest.raises(OSError):
        registry.create_workspace("Synthetic", "Owner", fail)
    with registry.connection() as db:
        assert db.execute("SELECT count(*) FROM workspaces").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM members").fetchone()[0] == 0


def test_bootstrap_helper_never_prints_or_overwrites_credentials(settings, monkeypatch, capsys):
    from scripts.pilot_admin import main

    monkeypatch.setenv("CLARITYOPS_DATA_DIR", str(settings.data_dir))
    destination = settings.data_dir / "owner.json"
    args = [
        "create-workspace",
        "--name",
        "Synthetic",
        "--owner",
        "Owner",
        "--credential-file",
        str(destination),
    ]
    main(args)
    content = destination.read_text()
    credential = json.loads(content)
    assert credential["access_token"] not in capsys.readouterr().out
    assert IdentityRegistry(settings).authenticate(credential["access_token"]).role == "owner"
    with pytest.raises(SystemExit):
        main(args)
    assert destination.read_text() == content


def test_revoked_owner_cannot_finish_inflight_indexing(companies):
    settings, registry, a, _, _ = companies
    actor = registry.authenticate(a["access_token"])
    second_owner = registry.add_member(actor, "Second owner", "owner")
    embeddings = FakeEmbeddings()
    original = embeddings.embed

    def revoke_while_indexing(texts, query=False):
        registry.revoke(registry.authenticate(second_owner["access_token"]), actor.member_id)
        return original(texts, query=query)

    with TestClient(create_app(settings, embeddings), headers=headers(a)) as c:
        with patch.object(embeddings, "embed", side_effect=revoke_while_indexing):
            assert upload(c, pdf_bytes()).status_code == 403
        assert c.get("/documents", headers=headers(second_owner)).json()["documents"] == []
        assert all(
            e["action"] != "document.uploaded"
            for e in c.get("/audit", headers=headers(second_owner)).json()["events"]
        )


@pytest.mark.parametrize("path", ["/members", "/audit"])
def test_new_owner_endpoints_require_auth(companies, path):
    settings, *_ = companies
    with TestClient(create_app(settings)) as c:
        assert c.get(path).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"auth_mode": "unknown"},
        {"deployment": "unknown"},
        {"deployment": "private"},
        {"deployment": "private", "auth_mode": "members"},
        {"cors_origins": ("*",)},
        {"cors_origins": ("https://example.com/path",)},
        {"cors_origins": ("https://user:password@example.com",)},
        {"cors_origins": ()},
    ],
)
def test_invalid_or_unsafe_deployment_configuration_fails_closed(settings, changes):
    with pytest.raises(ValueError):
        replace(settings, **changes)


def test_private_config_accepts_explicit_secure_origin(settings):
    config = replace(
        settings, deployment="private", auth_mode="members", cors_origins=("https://knowledge.example.com",)
    )
    assert config.deployment == "private"


def test_local_operator_can_recover_expired_owner(companies):
    settings, registry, a, _, _ = companies
    with registry.connection() as db:
        db.execute(
            "UPDATE members SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (a["member"]["id"],)
        )
    recovered = registry.issue_owner(a["workspace"]["id"], "Recovered owner")
    assert registry.authenticate(recovered["access_token"]).can_manage
    assert registry.authenticate(a["access_token"]) is None
    with TestClient(create_app(settings), headers=headers(recovered)) as c:
        assert any(e["action"] == "owner.recovered" for e in c.get("/audit").json()["events"])


def test_stopped_server_backup_restore_keeps_identity_data_and_isolation(companies, tmp_path):
    import shutil

    settings, _, a, b, employee = companies
    data = pdf_bytes()
    with TestClient(create_app(settings, FakeEmbeddings()), headers=headers(a)) as c:
        doc_id = upload(c, data).json()["document"]["id"]
    # The runbook requires stopping every server/CLI writer before copying the whole data root.
    backup = tmp_path / "cold-backup"
    restored = tmp_path / "restored"
    shutil.copytree(settings.data_dir, backup)
    shutil.copytree(backup, restored)
    with TestClient(create_app(replace(settings, data_dir=restored), FakeEmbeddings())) as c:
        assert c.get(f"/documents/{doc_id}/file", headers=headers(employee)).content == data
        assert c.delete(f"/documents/{doc_id}", headers=headers(employee)).status_code == 403
        assert c.get(f"/documents/{doc_id}/file", headers=headers(b)).status_code == 404
        assert c.get("/documents", headers=headers(a)).json()["documents"][0]["id"] == doc_id


def test_members_mode_does_not_import_legacy_shared_documents(companies):
    settings, _, a, _, _ = companies
    with TestClient(
        create_app(replace(settings, auth_mode="demo"), FakeEmbeddings()),
        headers={"X-ClarityOps-Token": TEST_TOKEN},
    ) as demo:
        old_id = upload(demo, pdf_bytes()).json()["document"]["id"]
    with TestClient(create_app(settings, FakeEmbeddings()), headers=headers(a)) as c:
        assert c.get("/documents").json()["documents"] == []
        assert c.get(f"/documents/{old_id}/file").status_code == 404
    # The legacy collection remains intact and can be deliberately resumed in local demo mode.
    with TestClient(
        create_app(replace(settings, auth_mode="demo"), FakeEmbeddings()),
        headers={"X-ClarityOps-Token": TEST_TOKEN},
    ) as demo:
        assert demo.get("/documents").json()["documents"][0]["id"] == old_id
