"""Encrypted, append-only document archive. No source-system writes."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from dotenv import dotenv_values

MAGIC = b"ABAE1\x00"
AAD = b"AutoBuchhaltung/archive/v1"
KDF = {"name": "scrypt", "n": 131072, "r": 8, "p": 1, "length": 32}


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".archive-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def seal(key: bytes, data: bytes, context: str) -> bytes:
    nonce = os.urandom(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, data, AAD + context.encode())


def unseal(key: bytes, data: bytes, context: str) -> bytes:
    if not data.startswith(MAGIC) or len(data) < len(MAGIC) + 28:
        raise ValueError("Unbekanntes oder beschädigtes Verschlüsselungsformat")
    offset = len(MAGIC)
    return AESGCM(key).decrypt(data[offset:offset + 12], data[offset + 12:], AAD + context.encode())


def password_key(password: str, salt: bytes) -> bytes:
    if not password:
        raise ValueError("ENCRYPTION_PASSWORD fehlt")
    return Scrypt(salt=salt, n=KDF["n"], r=KDF["r"], p=KDF["p"], length=32).derive(password.encode())


def wrapped_key(key: bytes, password: str) -> bytes:
    salt = os.urandom(32)
    return encoded({"version": 1, "cipher": "AES-256-GCM", "kdf": KDF,
                    "salt": base64.b64encode(salt).decode(),
                    "wrapped_key": base64.b64encode(seal(password_key(password, salt), key, "key")).decode()})


def unwrap_key(data: bytes, password: str) -> bytes:
    obj = json.loads(data)
    if obj.get("version") != 1 or obj.get("kdf") != KDF or obj.get("cipher") != "AES-256-GCM":
        raise ValueError("Nicht unterstützte Schlüsselparameter")
    key = unseal(password_key(password, base64.b64decode(obj["salt"], validate=True)),
                 base64.b64decode(obj["wrapped_key"], validate=True), "key")
    if len(key) != 32:
        raise ValueError("Ungültiger Datenschlüssel")
    return key


def within(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError("Pfad verlässt die Ablage")
    return path


def outside(repo: Path, target: Path) -> Path:
    target = target.resolve()
    from autobookkeeping.workspace import tool_root
    if target.is_relative_to(repo.resolve()) or target.is_relative_to(tool_root()):
        raise ValueError("Klartext/Exporte dürfen nur außerhalb des Repositorys liegen")
    return target


def clean_source(value: Any) -> Any:
    """Keep source fields, but never retain expiring URLs or authentication data."""
    if isinstance(value, list):
        return [clean_source(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_source(v) for k, v in value.items()
                if not re.search(r"url|token|password|secret|authorization", k, re.I)}
    return value


def money(value: Any) -> str | None:
    return None if value is None else str(Decimal(str(value)).quantize(Decimal("0.01")))


class Archive:
    def __init__(self, repo: Path, password: str | None = None):
        self.repo = repo.resolve()
        self.root = self.repo / "buchhaltung"
        self.password = password if password is not None else dotenv_values(self.repo / ".env").get("ENCRYPTION_PASSWORD", "")
        self.key_path = self.root / "key.json"
        self.key: bytes | None = None

    def init(self) -> None:
        if self.key_path.exists():
            self.unlock()
            return
        # Do not silently replace a lost key or initialize over an existing archive.
        if self.root.exists() and any(self.root.rglob("*.enc")):
            raise ValueError("Verschlüsselte Daten vorhanden, aber Schlüsseldatei fehlt")
        self.key = os.urandom(32)
        atomic(self.key_path, wrapped_key(self.key, self.password))
        self.key = None
        self.unlock()
        self.save_catalog({"schema_version": 1, "records": {}, "documents": {}, "imports": []})

    def unlock(self) -> bytes:
        if self.key is None:
            self.key = unwrap_key(self.key_path.read_bytes(), self.password)
        return self.key

    def read(self, name: str) -> bytes:
        return unseal(self.unlock(), within(self.root, name).read_bytes(), name)

    def write(self, name: str, data: bytes) -> None:
        path = within(self.root, name)
        if path.exists() and self.read(name) == data:
            return
        atomic(path, seal(self.unlock(), data, name))
        if self.read(name) != data:
            raise ValueError("Rückleseprüfung fehlgeschlagen")

    def catalog(self) -> dict:
        return json.loads(self.read("database.json.enc"))

    def save_catalog(self, catalog: dict) -> None:
        self.write("database.json.enc", encoded(catalog))
        # Public inventory exposes only opaque paths and ciphertext hashes.
        files = {}
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and (path.suffix == ".enc" or path == self.key_path):
                files[path.relative_to(self.root).as_posix()] = {"sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}
        atomic(self.root / "manifest.json", encoded({"schema_version": 1, "files": files}))

    def import_invoiz(self, source: Path) -> dict:
        source = outside(self.repo, source)
        manifest = json.loads((source / "manifest.json").read_bytes())
        if manifest.get("last_run", {}).get("status") != "complete":
            raise ValueError("Nur vollständige Backups importieren; Backup zuerst reparieren")
        self.init()
        catalog = self.catalog()
        downloads = manifest["downloads"]
        # Import only rows encountered in the successful latest run, not stale exports.
        run_start = manifest["last_run"]["started_at"]
        current = {k: v for k, v in downloads.items()
                   if v.get("status") == "complete" and v.get("last_seen_at", v.get("downloaded_at", "")) >= run_start}
        invoices = {v["source_id"] for v in current.values() if v["kind"] == "invoice_pdf"}
        expected = manifest["last_run"]["stats"]
        counts = Counter({"invoice": 0, "expense": 0, "documents": 0, "changed": 0})
        seen = set()
        for kind, directory in (("invoice", "Rechnungen"), ("expense", "Ausgaben")):
            for meta in sorted((source / directory).glob("*/Metadaten/*.json")):
                raw = json.loads(meta.read_bytes())
                detail = raw if kind == "invoice" else raw["expense"]
                if "id" not in detail:
                    # Foreign/manual exports are not part of the latest API backup.
                    continue
                source_id = str(detail["id"])
                if kind == "invoice" and source_id not in invoices:
                    continue
                # expense metadata is rewritten by every backup run.
                if kind == "expense" and meta.stat().st_mtime < datetime.fromisoformat(run_start).timestamp() - 2:
                    continue
                rid = f"invoiz:{kind}:{source_id}"
                if rid in seen:
                    raise ValueError("Doppelte aktive Quell-ID")
                seen.add(rid)
                date = detail.get("date") or detail.get("createdAt")
                year = str(date)[:4] if date and re.match(r"^\d{4}", str(date)) else "Unsortiert"
                category = "Rechnungen" if kind == "invoice" else "Ausgaben"
                gross = detail.get("totalGross") if kind == "invoice" else detail.get("priceTotal")
                net = detail.get("totalNet") if kind == "invoice" else None
                vat = detail.get("vatAmount") if kind == "expense" else (
                    Decimal(str(gross)) - Decimal(str(net)) if gross is not None and net is not None else None)
                if kind == "expense" and gross is not None and vat is not None:
                    net = Decimal(str(gross)) - Decimal(str(vat))
                record = {"id": rid, "source": "invoiz", "source_id": source_id, "kind": kind,
                          "year": year, "date": date, "number": detail.get("number"),
                          "status": detail.get("state", "recorded"), "currency": detail.get("currency", "EUR"),
                          "gross": money(gross), "net": money(net), "vat": money(vat),
                          "vat_rate": detail.get("vatPercent"),
                          "vat_basis": "source" if kind == "expense" else "gross_minus_net; rate not supplied",
                          "pay_date": detail.get("payDate"), "outstanding": money(detail.get("outstandingAmount")),
                          "source_record": clean_source(raw), "documents": []}
                attached = []
                if kind == "invoice":
                    attached = [v for v in current.values() if v["kind"] == "invoice_pdf" and v["source_id"] == source_id]
                else:
                    for receipt in raw.get("receiptDownloads", []):
                        if receipt.get("status") == "complete":
                            matches = [v for v in current.values() if v["relative_path"] == receipt.get("localFile")]
                            if len(matches) != 1:
                                raise ValueError("Beleg fehlt im aktuellen Manifest")
                            attached += matches
                for download in attached:
                    original = within(source, download["relative_path"])
                    data = original.read_bytes()
                    if len(data) != download["size"] or sha(data) != download["sha256"]:
                        raise ValueError("Backup-Datei beschädigt")
                    digest = sha(data)
                    # File names contain no customer names, numbers or original hashes.
                    opaque = sha((rid + ":" + digest).encode())
                    name = f"{year}/{category}/{opaque}{original.suffix.lower()}.enc"
                    self.write(name, data)
                    catalog["documents"][name] = {"sha256_plaintext": digest, "bytes_plaintext": len(data),
                                                   "record_id": rid, "source_path": download["relative_path"]}
                    record["documents"].append(name)
                    counts["documents"] += 1
                record["coverage"] = "complete" if record["documents"] else "missing_receipt"
                prior = catalog["records"].get(rid)
                if prior and prior["current"].get("source_detail") and prior["current"]["source_record"] == record["source_record"]:
                    for field in ("source_detail", "vat_rate", "vat_rates", "vat_basis", "small_business", "vat_breakdown"):
                        if field in prior["current"]:
                            record[field] = prior["current"][field]
                if prior is None or prior["current"] != record:
                    history = prior["history"] + [prior["current"]] if prior else []
                    catalog["records"][rid] = {"current": record, "history": history}
                    counts["changed"] += 1
                counts[kind] += 1
        if counts["invoice"] != expected["invoice_records"] or counts["expense"] != expected["expense_records"]:
            raise ValueError("Importanzahl stimmt nicht mit vollständigem Backup überein")
        from autobookkeeping.checklist import ChecklistStore
        checklist = self.repo / 'bookkeeping_checklist.json.enc'
        snapshot = clean_source(ChecklistStore(checklist).load() if checklist.exists() else json.loads((self.repo / 'bookkeeping_checklist.json').read_bytes()))
        catalog["workflow_checklist"] = snapshot
        provenance = {"source": "invoiz_backup", "run_id": manifest["last_run"]["id"],
                      "source_manifest_sha256": sha(encoded(manifest)), "counts": dict(counts)}
        if not any(i["run_id"] == provenance["run_id"] for i in catalog["imports"]):
            catalog["imports"].append(provenance)
        self.save_catalog(catalog)
        return dict(counts)

    def enrich_invoiz(self) -> dict:
        """Use the checked-in client for full invoice positions, taxes and payments."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from autobookkeeping.config import load_settings
        from autobookkeeping.invoiz_client import InvoizClient
        self.verify()
        catalog = self.catalog()
        client = InvoizClient(load_settings())
        client.token()  # Authenticate once before concurrent reads.
        rows = [v["current"] for v in catalog["records"].values() if v["current"]["kind"] == "invoice" and v["current"]["source"] == "invoiz"]
        def fetch(row):
            payload = client.get_invoice(row["source_id"])
            detail = payload.get("data", payload)
            if isinstance(detail.get("invoice"), dict):
                detail = detail["invoice"]
            if str(detail.get("id")) != row["source_id"]:
                raise ValueError("Detailantwort enthält falsche ID")
            if money(detail.get("totalGross")) != row["gross"] or money(detail.get("totalNet")) != row["net"]:
                raise ValueError("Quelldaten geändert; vollständiges Backup zuerst aktualisieren")
            return row, clean_source(detail)
        changed = 0
        failures = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(fetch, row): row["id"] for row in rows}
            for future in as_completed(futures):
                try:
                    row, detail = future.result()
                    updated = dict(row)
                    rates = sorted({p["vatPercent"] for p in detail.get("positions", []) if p.get("vatPercent") is not None})
                    updated.update(source_detail=detail, vat_rates=rates,
                                   vat_rate=rates[0] if len(rates) == 1 else None,
                                   vat_basis="invoice_positions" if rates else "source_detail; rate not supplied",
                                   small_business=detail.get("smallBusiness"), vat_breakdown=detail.get("vat"))
                    if updated != row:
                        previous = catalog["records"][row["id"]]
                        catalog["records"][row["id"]] = {"current": updated, "history": previous["history"] + [row]}
                        changed += 1
                except Exception as exc:
                    failures.append({"record_id": futures[future], "error_type": type(exc).__name__})
        catalog["enrichment_errors"] = failures
        self.save_catalog(catalog)
        self.verify()
        return {"ok": not failures, "invoice_details": len(rows) - len(failures), "changed": changed, "failed": len(failures)}

    def import_local(self, metadata: Path, documents: list[Path]) -> dict:
        """Archive existing local documents, without issuing/finalizing an invoice."""
        raw = clean_source(json.loads(outside(self.repo, metadata).read_bytes()))
        required = {"source_id", "kind", "date", "status", "currency", "gross", "net", "vat", "vat_rate"}
        if not required.issubset(raw) or raw["kind"] not in ("invoice", "expense"):
            raise ValueError("Metadaten entsprechen nicht dem lokalen Schema")
        date = datetime.fromisoformat(raw["date"])
        if not raw["source_id"] or raw["currency"] != "EUR":
            raise ValueError("Quell-ID und EUR-Währung erforderlich")
        if any(raw[k] is None for k in ("gross", "net", "vat")):
            raise ValueError("Lokale Belegbeträge müssen vollständig sein")
        gross, net, vat = (Decimal(money(raw[k])) for k in ("gross", "net", "vat"))
        if not all(v.is_finite() for v in (gross, net, vat)) or gross != net + vat:
            raise ValueError("Brutto muss gleich Netto plus Steuer sein")
        source_name = raw.get("source", "local")
        if source_name == "invoiz":
            raise ValueError("Invoiz-Daten mit import-invoiz übernehmen")
        self.init()
        self.verify()
        catalog = self.catalog()
        rid = f"{source_name}:{raw['kind']}:{raw['source_id']}"
        order_ids = {v for v in [raw.get("order_id"), *raw.get("order_id_aliases", [])] if v}
        # SRN / aliases identify invoice context, never create a second invoice record.
        if raw["kind"] == "invoice":
            checklist = catalog.get("workflow_checklist", {}).get("items", [])
            if isinstance(checklist, dict):
                checklist = list(checklist.values())
            for item in checklist:
                aliases = {v for v in [item.get("order_id"), *item.get("order_id_aliases", [])] if v}
                same_srn = raw.get("sales_record_number") and str(raw["sales_record_number"]) == str(item.get("sales_record_number"))
                if (order_ids & aliases or same_srn) and item.get("invoice_id"):
                    raise ValueError("Zum eBay-Kontext existiert bereits eine Rechnung in der Workflow-Checkliste")
            for other_id, value in catalog["records"].items():
                other = value["current"]
                other_ids = {v for v in [other.get("order_id"), *other.get("order_id_aliases", [])] if v}
                same_srn = raw.get("sales_record_number") and str(raw["sales_record_number"]) == str(other.get("sales_record_number"))
                same_number = raw.get("number") and other.get("number") == raw["number"]
                if other_id != rid and other["kind"] == "invoice" and (order_ids & other_ids or same_srn or same_number):
                    raise ValueError("Rechnung mit diesem Kontext/dieser Nummer bereits archiviert")
        year = str(date.year)
        folder = "Rechnungen" if raw["kind"] == "invoice" else "Ausgaben"
        row = dict(raw, id=rid, source=source_name, source_id=str(raw["source_id"]), year=year,
                   number=raw.get("number"), gross=money(gross), net=money(net), vat=money(vat),
                   source_record=raw, documents=[], coverage="complete", vat_basis="local_metadata")
        prepared = []
        for path in documents:
            path = outside(self.repo, path)
            data = path.read_bytes()
            if path.suffix.lower() != ".pdf" or b"%PDF-" not in data[:1024]:
                raise ValueError("Lokaler Import verlangt Original-PDFs")
            digest = sha(data)
            name = f"{year}/{folder}/{sha((rid + ':' + digest).encode())}.pdf.enc"
            prepared.append((name, data, digest))
            row["documents"].append(name)
        if not prepared:
            raise ValueError("Mindestens ein Original-PDF erforderlich")
        prior = catalog["records"].get(rid)
        if prior and prior["current"] == row:
            return {"ok": True, "changed": False, "record_id": rid}
        if prior:
            raise ValueError("Quell-ID vorhanden; Änderungen benötigen eine neue Korrektur-ID mit Bezug auf das Original")
        for name, data, digest in prepared:
            self.write(name, data)
            catalog["documents"][name] = {"sha256_plaintext": digest, "bytes_plaintext": len(data), "record_id": rid}
        catalog["records"][rid] = {"current": row, "history": []}
        self.save_catalog(catalog)
        self.verify()
        return {"ok": True, "changed": True, "record_id": rid}

    def verify(self) -> dict:
        allowed = {"key.json", "manifest.json", "README.md", "AGENTS.md"}
        for path in self.root.rglob("*"):
            if path.is_file():
                name = path.relative_to(self.root).as_posix()
                if name in allowed or name.endswith(".enc"):
                    continue
                if re.fullmatch(r"nachweise/[a-f0-9]{40}(?:[a-f0-9]{24})?\.json(?:\.ots(?:\.bak)?)?", name):
                    continue
                raise ValueError("Unerlaubte Klartext-/temporäre Datei in der Buchhaltungsablage")
        manifest = json.loads((self.root / "manifest.json").read_bytes())
        actual = {p.relative_to(self.root).as_posix() for p in self.root.rglob("*")
                  if p.is_file() and (p.suffix == ".enc" or p == self.key_path)}
        if actual != set(manifest["files"]):
            raise ValueError("Dateibestand weicht vom Manifest ab")
        for name, entry in manifest["files"].items():
            data = within(self.root, name).read_bytes()
            if sha(data) != entry["sha256"] or len(data) != entry["bytes"]:
                raise ValueError("Prüfsumme/Dateigröße stimmt nicht")
        catalog = self.catalog()
        if actual - {"key.json", "database.json.enc"} != set(catalog["documents"]):
            raise ValueError("Nicht inventarisierte Dokumente")
        for name, entry in catalog["documents"].items():
            data = self.read(name)
            if sha(data) != entry["sha256_plaintext"] or len(data) != entry["bytes_plaintext"]:
                raise ValueError("Entschlüsseltes Dokument stimmt nicht mit Datenbank überein")
        for value in catalog["records"].values():
            for record in [value["current"], *value["history"]]:
                if any(name not in catalog["documents"] for name in record["documents"]):
                    raise ValueError("Datensatz verweist auf fehlenden Beleg")
        for value in {**catalog.get("local_invoice_drafts", {}), **catalog.get("local_adjustment_drafts", {}), **catalog.get("local_expense_drafts", {})}.values():
            for record in [value["current"], *value["history"]]:
                if any(name not in catalog["documents"] for name in record["documents"]):
                    raise ValueError("Lokaler Entwurf verweist auf fehlenden Beleg")
                receipt = record.get("receipt_candidate")
                if receipt and receipt["document"] not in catalog["documents"]:
                    raise ValueError("Vorgemerkter Beleg fehlt")
                if record.get("kind") != "expense" and record["status"] in ("test_draft", "discarded") and record["number"] is not None:
                    raise ValueError("Testentwurf darf keine Rechnungsnummer verbrauchen")
        from autobookkeeping.ledger_validation import validate
        validate(catalog)
        return {"ok": True, "records": len(catalog["records"]), "documents": len(catalog["documents"])}

    def report(self, year: str | None = None) -> dict:
        self.verify()
        from autobookkeeping.homeoffice import eur_summary
        catalog = self.catalog()
        rows = [v["current"] for v in catalog["records"].values()]
        result = {}
        for y in sorted({r["year"] for r in rows} | set(catalog.get("homeoffice_allowances", {}))):
            if year and year != y:
                continue
            group = [r for r in rows if r["year"] == y]
            result[y] = {"invoices": sum(r["kind"] == "invoice" for r in group),
                         "expenses": sum(r["kind"] == "expense" for r in group),
                         "credit_notes": sum(r["kind"] == "credit_note" for r in group),
                         "corrections": sum(r["kind"] == "correction" for r in group),
                         "missing_receipts": sum(r["coverage"] != "complete" for r in group),
                         "unknown_vat_rates": sum(r.get("vat_rate") is None for r in group),
                         "invoice_gross": money(sum((Decimal(r["gross"]) for r in group if r["kind"] == "invoice" and r["gross"] is not None), Decimal(0))),
                         "expense_gross": money(sum((Decimal(r["gross"]) for r in group if r["kind"] == "expense" and r["gross"] is not None), Decimal(0))),
                         "eur_working": eur_summary(catalog, y)}
        return result

    def export(self, target: Path, year: str | None = None) -> dict:
        self.verify()
        target = outside(self.repo, target)
        if target.exists():
            raise ValueError("Exportziel muss neu sein, damit keine alten Klartextdateien zurückbleiben")
        catalog = self.catalog()
        rows = [v["current"] for v in catalog["records"].values() if year is None or v["current"]["year"] == year]
        exported = []
        for row in rows:
            row = dict(row)
            row["documents"] = [name[:-4] for name in row["documents"]]
            for name in row["documents"]:
                path = outside(self.repo, within(target, name))
                atomic(path, self.read(name + ".enc"))
            exported.append(row)
        atomic(outside(self.repo, target / "database.json"), encoded({"schema_version": 1, "records": exported,
               "imports": catalog["imports"], "basis": "Dokumentdatum; Bruttobelegwerte, keine steuerliche EÜR"}))
        template = (__import__("autobookkeeping.workspace", fromlist=["tool_root"]).tool_root() / "scripts/archive_view.html").read_bytes()
        atomic(outside(self.repo, target / "index.html"), template)
        return {"ok": True, "records": len(exported), "directory": str(target)}


def git(repo: Path, *args: str) -> bytes:
    from autobookkeeping.workspace import assert_git_root, git as workspace_git
    if (repo / "HEAD").exists() and (repo / "objects").is_dir():
        if args[0] not in ("cat-file", "ls-tree", "show", "rev-parse"): raise ValueError("Historienrepo nur lesbar")
    else: assert_git_root(repo)
    return workspace_git(repo, *args)


@contextmanager
def historical_repo(repo, commit):
    try:
        git(repo, "cat-file", "-e", commit + "^{commit}")
    except subprocess.CalledProcessError:
        pass
    else:
        yield repo
        return
    path = repo / "migration/legacy-repository.bundle.enc"
    if not path.exists(): raise ValueError("Historisches Commitobjekt fehlt")
    from autobookkeeping.workspace import git_environment
    with tempfile.TemporaryDirectory(prefix="bookkeeping-history-") as temp:
        bundle = Path(temp) / "legacy.bundle"
        atomic(bundle, unseal(Archive(repo).unlock(), path.read_bytes(), "migration/legacy-repository.bundle"))
        bare = Path(temp) / "history.git"
        subprocess.run(["git", "clone", "--bare", str(bundle), str(bare)], env=git_environment(), capture_output=True, check=True)
        git(bare, "cat-file", "-e", commit + "^{commit}")
        yield bare


def committed_hashes(repo, commit, names):
    # One Git process avoids hundreds of Windows process launches per timestamp.
    from autobookkeeping.workspace import git_environment
    requests = "".join(commit + ":" + n + "\n" for n in names).encode()
    result = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], input=requests,
                            env=git_environment(), capture_output=True, check=True, timeout=60).stdout
    stream = __import__("io").BytesIO(result); hashes = {}
    for name in names:
        header = stream.readline().split()
        if len(header) != 3 or header[1] != b"blob": raise ValueError("Historisches Objekt fehlt")
        hashes[name] = sha(stream.read(int(header[2])))
        if stream.read(1) != b"\n": raise ValueError("Ungültige Git-Objektantwort")
    if stream.read(): raise ValueError("Unerwartete zusätzliche Git-Objekte")
    return hashes


def checkpoint_names(repo, commit, version):
    names = git(repo, "ls-tree", "-r", "--name-only", commit).decode().splitlines()
    return sorted(n for n in names if n.startswith("buchhaltung/") and "/nachweise/" not in n
                  or version >= 2 and (n in ("tool-version.json", "bookkeeping_checklist.json.enc", "workspace.json", ".bookkeeping-data.json")
                                      or n.startswith("migration/")))


def checkpoint(repo: Path, revision: str = "HEAD") -> Path:
    # Timestamp a prior data commit; the proof is committed separately, avoiding recursion.
    commit = git(repo, "rev-parse", "--verify", revision + "^{commit}").decode().strip()
    version = 2 if (repo / ".bookkeeping-data.json").exists() else 1
    files = committed_hashes(repo, commit, checkpoint_names(repo, commit, version))
    if not files or "buchhaltung/manifest.json" not in files:
        raise ValueError("Commit enthält keine vollständige Buchhaltungsablage")
    # Reject an uncommitted archive before attributing it to HEAD.
    for name, digest in files.items():
        if sha(within(repo, name).read_bytes()) != digest:
            raise ValueError("Buchhaltung zuerst committen")
    tracked = {n for n in files if n.startswith("buchhaltung/")}
    local = {p.relative_to(repo).as_posix() for p in (repo / "buchhaltung").rglob("*")
             if p.is_file() and "/nachweise/" not in p.relative_to(repo).as_posix()}
    if local != tracked:
        raise ValueError("Nicht eingecheckte Buchhaltungsdateien vorhanden")
    obj = git(repo, "cat-file", "commit", commit)
    data = {"schema_version": version, "git_commit": commit,
            "git_commit_object_sha256": sha(b"commit " + str(len(obj)).encode() + b"\0" + obj),
            "files_sha256": files}
    path = repo / "buchhaltung/nachweise" / f"{commit}.json"
    if path.exists() and path.read_bytes() != encoded(data):
        raise ValueError("Abweichender existierender Nachweis")
    atomic(path, encoded(data))
    return path


def verify_checkpoint(repo: Path, path: Path) -> dict:
    data = json.loads(path.read_bytes())
    commit = data["git_commit"]
    if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", commit):
        raise ValueError("Ungültiger Git-Hash")
    with historical_repo(repo, commit) as history:
        obj = git(history, "cat-file", "commit", commit)
        if sha(b"commit " + str(len(obj)).encode() + b"\0" + obj) != data["git_commit_object_sha256"]:
            raise ValueError("Commitobjekt verändert")
        expected = checkpoint_names(history, commit, data["schema_version"])
        if set(data["files_sha256"]) != set(expected): raise ValueError("Unvollständiger Nachweis")
        if committed_hashes(history, commit, expected) != data["files_sha256"]:
            raise ValueError("Historischer Beleg verändert")
        return {"git_commit": commit, "git_integrity": True, "files": len(expected)}


def cd_export(archive: Archive, target: Path) -> dict:
    archive.verify()
    target = outside(archive.repo, target)
    if target.exists():
        raise ValueError("CD-Exportziel muss neu sein")
    # Require committed current archive including proofs.
    if git(archive.repo, "status", "--porcelain", "--", "buchhaltung", "migration", "workspace.json", "tool-version.json", "bookkeeping_checklist.json.enc").strip():
        raise ValueError("Buchhaltung und Nachweise zuerst committen")
    import shutil
    target.mkdir(parents=True)
    shutil.copytree(archive.root, target / "buchhaltung")
    with tempfile.TemporaryDirectory(prefix="buchhaltung-bundle-") as temp:
        bundle = Path(temp) / "repository.bundle"
        git(archive.repo, "bundle", "create", str(bundle), "--all")
        git(archive.repo, "bundle", "verify", str(bundle))
        data = bundle.read_bytes()
        cipher = seal(archive.unlock(), data, "repository.bundle")
        if unseal(archive.unlock(), cipher, "repository.bundle") != data:
            raise ValueError("Bundle-Verschlüsselung fehlgeschlagen")
        atomic(target / "repository.bundle.enc", cipher)
    from autobookkeeping.workspace import tool_root
    tool = tool_root()
    if git(tool, "status", "--porcelain").strip(): raise ValueError("Tooländerungen zuerst abschließen")
    git(tool, "bundle", "create", str(target / "tool.bundle"), "--all")
    atomic(target / 'scripts/restore_backup.py', (tool / 'scripts/restore_backup.py').read_bytes())
    if (archive.repo / "migration").exists(): shutil.copytree(archive.repo / "migration", target / "migration")
    for name in (".bookkeeping-data.json", "workspace.json", "tool-version.json", "bookkeeping_checklist.json.enc"):
        if (archive.repo / name).exists(): atomic(target / name, (archive.repo / name).read_bytes())
    for name in ("src/autobookkeeping/workspace.py", "scripts/bookkeeping_action.py", "scripts/publish_bookkeeping.py", "src/autobookkeeping/publication.py", "src/autobookkeeping/models.py", "pyproject.toml", "scripts/bookkeeping_archive.py", "scripts/local_invoice.py", "scripts/receipt.py", "scripts/homeoffice.py", "scripts/install_receipt_skill.py", "scripts/ots_windows.py", "scripts/archive_view.html", "scripts/build_bookkeeping_dashboard.py", "scripts/dashboard_view.html", "dashboard.html", "src/autobookkeeping/archive.py", "src/autobookkeeping/local_invoices.py", "src/autobookkeeping/timestamps.py", "src/autobookkeeping/taxes.py", "src/autobookkeeping/adjustments.py", "src/autobookkeeping/cashflow.py", "src/autobookkeeping/dashboard.py", "src/autobookkeeping/ledger_validation.py", "src/autobookkeeping/receipts.py", "src/autobookkeeping/homeoffice.py", "skills/beleg-import/SKILL.md", "skills/beleg-import/agents/openai.yaml"):
        source = archive.repo / name if name == "dashboard.html" else tool / name
        atomic(within(target, name), source.read_bytes())
    atomic(target / "WIEDERHERSTELLUNG.txt", (
        "Verschlüsselte Buchhaltungssicherung. ENCRYPTION_PASSWORD getrennt aufbewahren!\n"
        "Python 3.11+, Git und Abhängigkeiten aus pyproject.toml werden benötigt.\n"
        "git clone tool.bundle NEUES_TOOL\n"
        "Abhaengigkeiten installieren: python -m pip install -e NEUES_TOOL\n"
        "python NEUES_TOOL/scripts/restore_backup.py PFAD_DER_CD --password-file PFAD_ENV --output PFAD_AUSSERHALB\n"
        "git clone PFAD_AUSSERHALB/repository.bundle NEUES_TOOL/daten\n"
        "Danach NEUES_TOOL/daten/.env anlegen und dort vom Toolordner aus scripts/bookkeeping_archive.py verify ausführen.\n"
        "SHA256SUMS.json mit cd-verify prüfen; zusätzlich Nachweise verifizieren.\n"
        "CD finalisieren, zurücklesen und erst dann als gesichert behandeln.\n").encode())
    hashes = {p.relative_to(target).as_posix(): sha(p.read_bytes()) for p in target.rglob("*") if p.is_file()}
    atomic(target / "SHA256SUMS.json", encoded(hashes))
    return {"ok": True, "directory": str(target), "files": len(hashes),
            "bytes": sum(p.stat().st_size for p in target.rglob("*") if p.is_file()), "burned": False}


def cd_verify(target: Path) -> dict:
    target = target.resolve()
    hashes = json.loads((target / "SHA256SUMS.json").read_bytes())
    actual = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file() and p.name != "SHA256SUMS.json"}
    if set(hashes) != actual:
        raise ValueError("Dateien im Sicherungsmedium fehlen oder wurden hinzugefügt")
    for name, digest in hashes.items():
        if sha(within(target, name).read_bytes()) != digest:
            raise ValueError("Sicherungsmedium hat eine abweichende Prüfsumme")
    return {"ok": True, "files": len(hashes)}
