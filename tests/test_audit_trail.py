import copy
import csv
import json

import pytest

from autobookkeeping.archive import Archive, atomic, encoded, seal, sha
from autobookkeeping.audit_trail import FIELD, prepare, validate
from autobookkeeping.inspection_export import nodes
from autobookkeeping.local_invoices import LocalInvoices
from test_archive import fixture_document


def test_replay_preserves_edits_deletions_types_and_chain():
    catalog = {"documents": {}, "settings": {"rate": 0, "note": "SYNTHETIC ORIGINAL"}, "list": [1, None]}
    prepare(None, catalog, "a" * 40)
    before = copy.deepcopy(catalog)
    catalog["settings"]["rate"] = False
    del catalog["settings"]["note"]
    catalog["list"].append("SYNTHETIC NEW")
    prepare(before, catalog, "b" * 40)
    assert validate(catalog)["events"] == 2
    assert catalog[FIELD]["events"][-1]["tool_commit"] == "b" * 40
    delta = catalog[FIELD]["events"][-1]["changes"]
    assert any(v["before"] == "SYNTHETIC ORIGINAL" and not v["after_exists"] for v in delta)
    assert any(v["path"] == ["settings", "rate"] for v in delta)
    broken = copy.deepcopy(catalog)
    broken[FIELD]["events"][0]["at"] = "2020-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):
        validate(broken)
    broken = copy.deepcopy(catalog)
    broken["settings"]["rate"] = 99
    with pytest.raises(ValueError):
        validate(broken)
    broken = copy.deepcopy(catalog)
    del broken[FIELD]
    with pytest.raises(ValueError):
        prepare(catalog, broken)


def test_legacy_baseline_is_explicit_and_noop_preserves_ciphertext(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    archive = Archive(repo, "synthetic-password"); archive.init()
    legacy = {"schema_version": 1, "records": {}, "documents": {}, "imports": []}
    atomic(archive.root / "database.json.enc", seal(archive.unlock(), encoded(legacy), "database.json.enc"))
    assert validate(archive.catalog())["status"] == "legacy_without_trail"
    catalog = archive.catalog(); catalog["settings"] = {"synthetic": True}
    archive.save_catalog(catalog)
    assert catalog[FIELD]["baseline"] == legacy
    assert catalog[FIELD]["baseline_kind"] == "existing_state"
    original = (archive.root / "database.json.enc").read_bytes()
    archive.save_catalog(archive.catalog())
    assert (archive.root / "database.json.enc").read_bytes() == original
    assert archive.verify()["audit"]["events"] == 1


def test_original_overwrite_and_inventory_removal_rejected(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    archive = Archive(repo, "synthetic-password")
    _, meta, pdf = fixture_document(tmp_path); archive.import_local(meta, [pdf])
    catalog = archive.catalog()
    name = next(iter(catalog["documents"]))
    cipher = (archive.root / name).read_bytes()
    with pytest.raises(ValueError):
        archive.write(name, b"%PDF-1.4 DIFFERENT ORIGINAL")
    assert (archive.root / name).read_bytes() == cipher
    archive.write(name, pdf.read_bytes())
    assert (archive.root / name).read_bytes() == cipher
    for modification in ("remove", "digest"):
        changed = copy.deepcopy(catalog)
        if modification == "remove":
            del changed["documents"][name]
        else:
            changed["documents"][name]["sha256_plaintext"] = "0" * 64
        with pytest.raises(ValueError):
            archive.save_catalog(changed)
    assert archive.catalog() == catalog


def test_recovery_after_catalog_saved_does_not_duplicate_audit_event(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; repo.mkdir()
    archive = Archive(repo, "synthetic-password"); archive.init()
    workflow = LocalInvoices(archive)
    before = archive.catalog(); after = copy.deepcopy(before)
    after["settings"] = {"note": "SYNTHETIC PRIVATE VALUE"}
    original = archive.save_catalog

    def saved_then_crashed(value):
        original(value)
        raise OSError("Synthetic power loss after save")

    monkeypatch.setattr(archive, "save_catalog", saved_then_crashed)
    with pytest.raises(OSError):
        workflow.commit(before, after, {})
    persisted = archive.catalog()
    assert b"SYNTHETIC PRIVATE VALUE" not in workflow.journal.read_bytes()
    monkeypatch.setattr(archive, "save_catalog", original)
    assert workflow.recover()
    assert archive.catalog() == persisted
    assert archive.verify()["audit"]["events"] == 2


def test_complete_csv_export_preserves_private_strings_versions_and_relations(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    archive = Archive(repo, "synthetic-password")
    _, meta, pdf = fixture_document(tmp_path); archive.import_local(meta, [pdf])
    catalog = archive.catalog()
    text = 'SYNTHETIC; "Name"\nSecond line / ~ \u00e4'
    catalog["additional"] = {"/key~": text, "empty": {}, "unknown": None, "flag": False}
    catalog["records"]["imported:invoice:1"]["history"].append(copy.deepcopy(catalog["records"]["imported:invoice:1"]["current"]))
    archive.save_catalog(catalog)
    target = tmp_path / "inspection"
    archive.export(target, year="2099")
    with (target / "catalog-nodes.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=";"))
    assert rows == list(nodes(catalog))
    assert next(v for v in rows if v["path"] == "/additional/~1key~0")["value"] == text
    with (target / "records.csv").open(encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream, delimiter=";"))
    assert len(records) == 2 and records[0]["number"] == "0001"
    description = json.loads((target / "data-description.json").read_bytes())
    assert description["scope"] == "complete"
    assert description["tables"]["records.csv"]["columns"]["gross"]["type"] == "decimal"
    for name, table in description["tables"].items():
        assert sha((target / name).read_bytes()) == table["sha256"]
    assert not any(text.encode() in p.read_bytes() for p in archive.root.rglob("*") if p.is_file())
