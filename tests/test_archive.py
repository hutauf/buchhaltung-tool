import json
import subprocess
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from autobookkeeping.archive import Archive, encoded, sha, outside, seal, unseal, wrapped_key, unwrap_key, cd_verify, checkpoint, verify_checkpoint


def test_authenticated_encryption_and_wrapping():
    key = bytes(range(32))
    wrapped = wrapped_key(key, "test-password")
    assert key not in wrapped
    assert unwrap_key(wrapped, "test-password") == key
    with pytest.raises(InvalidTag):
        unwrap_key(wrapped, "wrong-password")
    cipher = seal(key, b"private buyer PDF", "2011/Rechnungen/x.pdf.enc")
    assert b"private buyer" not in cipher
    assert cipher != seal(key, b"private buyer PDF", "2011/Rechnungen/x.pdf.enc")
    assert unseal(key, cipher, "2011/Rechnungen/x.pdf.enc") == b"private buyer PDF"
    with pytest.raises(InvalidTag):
        unseal(key, cipher[:-1] + bytes([cipher[-1] ^ 1]), "2011/Rechnungen/x.pdf.enc")
    with pytest.raises(InvalidTag):
        unseal(key, cipher, "wrong-path")


def fixture_document(root: Path):
    source = root / "source"; source.mkdir()
    pdf = source / "invoice.pdf"; pdf.write_bytes(b"%PDF-1.4 private buyer")
    meta = source / "metadata.json"
    meta.write_bytes(encoded({"source":"imported","source_id":"1","kind":"invoice","number":"0001", "date":"2011-10-01", "status":"paid", "currency":"EUR", "gross":"119.00", "net":"100.00", "vat":"19.00", "vat_rate":19, "buyer":{"name":"PRIVATE NAME"}}))
    return source, meta, pdf


def test_import_idempotence_immutable_original_and_tampering(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    archive = Archive(repo, "test-password")
    source, meta, pdf = fixture_document(tmp_path)
    assert archive.import_local(meta, [pdf])["changed"]
    assert archive.verify()["documents"] == 1
    before = {p: p.read_bytes() for p in archive.root.rglob("*") if p.is_file()}
    assert not archive.import_local(meta, [pdf])["changed"]
    assert all(p.read_bytes() == value for p, value in before.items())
    assert b"PRIVATE NAME" not in b"".join(before.values())
    row = archive.catalog()["records"]["imported:invoice:1"]["current"]
    assert row["gross"] == "119.00" and row["vat"] == "19.00" and row["vat_rate"] == 19
    raw = json.loads(meta.read_bytes()); raw.update(gross="120.00", net="101.00"); meta.write_bytes(encoded(raw))
    with pytest.raises(ValueError): archive.import_local(meta, [pdf])
    assert archive.catalog()["records"]["imported:invoice:1"]["current"] == row
    path = archive.root / row["documents"][0]
    ciphertext = path.read_bytes()
    tampered = ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])
    assert tampered != ciphertext
    path.write_bytes(tampered)
    with pytest.raises(ValueError): archive.verify()


def test_outside_and_traversal_and_lost_key(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    with pytest.raises(ValueError):
        outside(repo, repo / "klartext")
    archive = Archive(repo, "password"); archive.init()
    with pytest.raises(ValueError):
        archive.write("../escape.enc", b"test")
    archive.key_path.unlink()
    with pytest.raises(ValueError):
        Archive(repo, "password").init()


def test_cd_integrity(tmp_path):
    (tmp_path / "test.enc").write_bytes(b"encrypted")
    (tmp_path / "SHA256SUMS.json").write_bytes(encoded({"test.enc": sha(b"encrypted")}))
    assert cd_verify(tmp_path)["ok"]
    (tmp_path / "test.enc").write_bytes(b"changed")
    with pytest.raises(ValueError):
        cd_verify(tmp_path)


def test_historical_git_checkpoint_and_uncommitted_rejection(tmp_path):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args])
    git("init"); git("config", "user.email", "test@example.invalid"); git("config", "user.name", "Test")
    root = tmp_path / "buchhaltung"; root.mkdir()
    (root / "manifest.json").write_bytes(b"{}")
    (root / "test.enc").write_bytes(b"encrypted")
    git("add", "buchhaltung"); git("commit", "-m", "data")
    proof = checkpoint(tmp_path)
    assert verify_checkpoint(tmp_path, proof)["git_integrity"]
    (root / "test.enc").write_bytes(b"changed")
    # Historical verification still works, current changed state cannot be stamped as HEAD.
    assert verify_checkpoint(tmp_path, proof)["git_integrity"]
    with pytest.raises(ValueError):
        checkpoint(tmp_path)


def test_local_import_checks_amounts_and_duplicate_invoice(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    archive = Archive(repo, "test-password")
    metadata = tmp_path / "metadata.json"
    pdf = tmp_path / "invoice.pdf"; pdf.write_bytes(b"%PDF-1.4 PRIVATE CUSTOMER")
    raw = {"source_id": "one", "kind": "invoice", "date": "2011-10-03", "status": "issued", "currency": "EUR",
           "number": "LOCAL-1", "gross": "119.00", "net": "100.00", "vat": "19.00", "vat_rate": 19, "sales_record_number": "42"}
    metadata.write_bytes(encoded(raw))
    assert archive.import_local(metadata, [pdf])["changed"]
    assert not archive.import_local(metadata, [pdf])["changed"]
    raw["source_id"] = "two"; metadata.write_bytes(encoded(raw))
    with pytest.raises(ValueError):
        archive.import_local(metadata, [pdf])
    raw["number"] = "LOCAL-2"; raw["sales_record_number"] = "43"; raw["gross"] = "120.00"; metadata.write_bytes(encoded(raw))
    with pytest.raises(ValueError):
        archive.import_local(metadata, [pdf])
    (archive.root / "oops.pdf").write_bytes(b"%PDF-private")
    with pytest.raises(ValueError):
        archive.verify()


def test_export_only_outside_repo_and_original_pdf(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    scripts = repo / "scripts"; scripts.mkdir()
    (scripts / "archive_view.html").write_bytes(b"<!doctype html>view")
    (repo / "bookkeeping_checklist.json").write_text('{"items": []}')
    source, meta, pdf = fixture_document(tmp_path)
    archive = Archive(repo, "test-password"); archive.import_local(meta, [pdf])
    with pytest.raises(ValueError):
        archive.export(repo / "output")
    target = tmp_path / "view"
    assert archive.export(target)["records"] == 1
    assert next(target.rglob("*.pdf")).read_bytes() == pdf.read_bytes()
    with pytest.raises(ValueError):
        archive.export(target)
