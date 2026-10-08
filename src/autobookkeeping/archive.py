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
        if path.exists():
            if self.read(name) == data:
                return
            if name != "database.json.enc":
                raise ValueError("Vorhandenes Original darf nicht überschrieben werden")
        atomic(path, seal(self.unlock(), data, name))
        if self.read(name) != data:
            raise ValueError("Rückleseprüfung fehlgeschlagen")

    def catalog(self) -> dict:
        return json.loads(self.read("database.json.enc"))

    def prepare_catalog(self, catalog: dict) -> None:
        from autobookkeeping.audit_trail import prepare
        from autobookkeeping.workspace import tool_root, git as tool_git
        try:
            revision = tool_git(tool_root(), "rev-parse", "HEAD").decode().strip()
        except (OSError, subprocess.CalledProcessError):
            revision = None
        prior = self.catalog() if (self.root / "database.json.enc").exists() else None
        prepare(prior, catalog, revision)

    def save_catalog(self, catalog: dict) -> None:
        self.prepare_catalog(catalog)
        self.write("database.json.enc", encoded(catalog))
        # Public inventory exposes only opaque paths and ciphertext hashes.
        files = {}
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and (path.suffix == ".enc" or path == self.key_path):
                files[path.relative_to(self.root).as_posix()] = {"sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}
        atomic(self.root / "manifest.json", encoded({"schema_version": 1, "files": files}))

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
        for row in catalog.get('archive_evidence',{}).values():
            if not row.get('documents') or any(n not in catalog['documents'] for n in row['documents']):
                raise ValueError('Zusatznachweis verweist auf fehlendes Original')
        from autobookkeeping.ledger_validation import validate
        validate(catalog)
        from autobookkeeping.audit_trail import validate as validate_trail
        audit = validate_trail(catalog)
        return {"ok": True, "records": len(catalog["records"]), "documents": len(catalog["documents"]), "audit": audit}

    def import_evidence(self, source: Path, metadata: Path) -> dict:
        """Preserve supporting business originals without inventing an expense."""
        from datetime import date
        from autobookkeeping.local_invoices import LocalInvoices
        source=outside(self.repo, source); metadata=outside(self.repo, metadata)
        raw=json.loads(metadata.read_bytes())
        if set(raw) != {'date','description','verification_basis'} or not all(isinstance(v,str) and v.strip() for v in raw.values()):
            raise ValueError('Nachweis benötigt Datum, Beschreibung und konkrete Prüfbasis')
        day=date.fromisoformat(raw['date'])
        extension=source.suffix.lower()
        if extension not in ('.pdf','.xml','.csv','.json','.eml','.txt','.png','.jpg','.jpeg') or source.stat().st_size>100_000_000:
            raise ValueError('Nachweisformat/Größe nicht unterstützt')
        data=source.read_bytes(); digest=sha(data)
        if not data:raise ValueError('Nachweis ist leer')
        self.verify();before=self.catalog()
        existing=[n for n,e in before['documents'].items() if e['sha256_plaintext']==digest]
        if existing:return {'ok':True,'changed':False,'documents':existing,'booked':False}
        import copy
        after=copy.deepcopy(before)
        name=f'{day.year}/Unterlagen/{digest}{extension}.enc'
        rid='evidence:'+digest
        after['documents'][name]={'record_id':rid,'role':'supporting_evidence','sha256_plaintext':digest,'bytes_plaintext':len(data)}
        after.setdefault('archive_evidence',{})[rid]=dict(raw,id=rid,documents=[name],source_sha256=digest)
        LocalInvoices(self).commit(before,after,{name:data})
        return {'ok':True,'changed':True,'id':rid,'documents':[name],'booked':False}

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
        # A year is a view annotation, never a destructive archive selection.
        rows = [v["current"] for v in catalog["records"].values()]
        exported = []
        files = {}
        for name, entry in catalog['documents'].items():
            plain = name[:-4]
            atomic(outside(self.repo, within(target, plain)), self.read(name))
            files[name] = dict(entry, exported_path=plain)
        for row in rows:
            row = dict(row)
            row["documents"] = [name[:-4] for name in row["documents"]]
            exported.append(row)
        atomic(target / 'catalog.json', encoded(catalog))
        from autobookkeeping.inspection_export import write_tables
        table_hashes = write_tables(target, catalog, files)
        checklist = self.repo / 'bookkeeping_checklist.json.enc'
        if checklist.exists():
            atomic(target / 'bookkeeping_checklist.json', unseal(self.unlock(), checklist.read_bytes(), 'bookkeeping_checklist.json'))
        elif (self.repo / 'bookkeeping_checklist.json').exists():
            atomic(target / 'bookkeeping_checklist.json', (self.repo / 'bookkeeping_checklist.json').read_bytes())
        proof_dir = self.root / 'nachweise'
        for path in proof_dir.glob('*'):
            if path.is_file():atomic(target / 'nachweise' / path.name, path.read_bytes())
        for name in ('workspace.json', 'tool-version.json', 'timestamp-status.json'):
            if (self.repo / name).exists():atomic(target / name, (self.repo / name).read_bytes())
        for name in ('AGENTS.md','verfahrensdokumentation.md','buchhaltung/README.md','buchhaltung/AGENTS.md'):
            if (self.repo / name).exists():atomic(target / 'dokumentation' / name,(self.repo / name).read_bytes())
        for path in (self.repo / 'migration').rglob('*.enc'):
            atomic(target / 'migration' / path.relative_to(self.repo / 'migration'), path.read_bytes())
        atomic(target / 'export-manifest.json', encoded({'version':2,'scope':'complete',
            'catalog_sha256':sha(encoded(catalog)), 'documents':files, 'view_year':year,
            'inspection_files_sha256':table_hashes,
            'retention_years':11, 'secrets_included':False}))
        atomic(outside(self.repo, target / "database.json"), encoded({"schema_version": 1, "records": exported,
               "imports": catalog["imports"], "view_year":year,
               "basis": "Vollständiger Bestand; Dokumentdatum und Bruttobelegwerte, keine steuerliche EÜR. Vollständige Historien/Zahlungen/Einstellungen in catalog.json."}))
        template = (__import__("autobookkeeping.workspace", fromlist=["tool_root"]).tool_root() / "scripts/archive_view.html").read_bytes()
        atomic(outside(self.repo, target / "index.html"), template)
        return {"ok": True, "records": len(exported), "documents":len(files), "complete":True, "directory": str(target)}


def git(repo: Path, *args: str) -> bytes:
    from autobookkeeping.workspace import assert_git_root, git as workspace_git
    if (repo / "HEAD").exists() and (repo / "objects").is_dir():
        if args[0] not in ("cat-file", "ls-tree", "show", "rev-parse"): raise ValueError("Historienrepo nur lesbar")
    else: assert_git_root(repo)
    return workspace_git(repo, *args)


@contextmanager
def historical_repo(repo, commit, password=None):
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
        atomic(bundle, unseal(Archive(repo,password).unlock(), path.read_bytes(), "migration/legacy-repository.bundle"))
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


def verify_checkpoint(repo: Path, path: Path, password=None) -> dict:
    data = json.loads(path.read_bytes())
    commit = data["git_commit"]
    if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", commit):
        raise ValueError("Ungültiger Git-Hash")
    with historical_repo(repo, commit, password) as history:
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
    if git(archive.repo, "status", "--porcelain", "--", "buchhaltung", "migration", "workspace.json", "tool-version.json", "bookkeeping_checklist.json.enc", "timestamp-status.json", "verfahrensdokumentation.md", "AGENTS.md", "README.md", "dashboard.html").strip():
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
    for name in (".bookkeeping-data.json", "workspace.json", "tool-version.json", "bookkeeping_checklist.json.enc", "timestamp-status.json", "verfahrensdokumentation.md", "AGENTS.md", "README.md"):
        if (archive.repo / name).exists(): atomic(target / name, (archive.repo / name).read_bytes())
    # Include every tracked runtime module, schema, skill and procedure document.
    names = git(tool, 'ls-files', '-z').decode().split('\0')
    for name in names:
        if name and (name.startswith(('src/', 'scripts/', 'skills/', 'docs/')) or name in ('pyproject.toml','README.md','LICENSE','THIRD_PARTY_NOTICES.md','CHANGELOG.md','AGENTS.md')):
            atomic(within(target, name), (tool / name).read_bytes())
    if (archive.repo / 'dashboard.html').exists():atomic(target / 'dashboard.html',(archive.repo / 'dashboard.html').read_bytes())
    from autobookkeeping.local_invoices import now
    atomic(target / 'BACKUP.json', encoded({'version':1, 'prepared_at':now(),
           'data_commit':git(archive.repo,'rev-parse','HEAD').decode().strip(),
           'tool_commit':git(tool,'rev-parse','HEAD').decode().strip()}))
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
