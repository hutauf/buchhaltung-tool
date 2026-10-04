"""Durable, narrowly scoped Git/push/OTS completion after local archive writes."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

from filelock import FileLock
from autobookkeeping.archive import Archive, atomic, checkpoint, encoded, sha, verify_checkpoint
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError
from autobookkeeping.timestamps import load_proof
from autobookkeeping.workspace import assert_data_repo, assert_tool_clean, tool_root, git as workspace_git


def git(repo, *args):
    assert_data_repo(repo)
    return workspace_git(repo, *args)


def data_path(name):
    return name in ("bookkeeping_checklist.json.enc", "buchhaltung/key.json", "buchhaltung/database.json.enc", "buchhaltung/manifest.json") or (
        name.startswith("buchhaltung/") and name.endswith(".enc") and "/nachweise/" not in name)


class Publication:
    def __init__(self, repo, action, enabled=True, mode="data"):
        self.repo = Path(repo).resolve(); self.action = action; self.enabled = enabled; self.result = None
        self.path = self.repo / "output/publication.json"
        self.lock = FileLock(self.repo / "output/publication.lock", timeout=0)
        self.mode = mode

    def digest(self):
        path = self.repo / "buchhaltung/manifest.json"
        checklist = self.repo / 'bookkeeping_checklist.json.enc'
        return sha(encoded({'archive':sha(path.read_bytes()) if path.exists() else None,
                            'checklist':sha(checklist.read_bytes()) if checklist.exists() else None}))

    def names(self, *args):
        return [s for s in git(self.repo, *args).decode("utf8").split("\0") if s]

    def write(self):
        atomic(self.path, encoded(self.state))

    def check_code(self):
        assert_tool_clean()

    def __enter__(self):
        if not self.enabled: return self
        assert_data_repo(self.repo, remote=True)
        self.path.parent.mkdir(exist_ok=True); self.lock.acquire()
        try:
            if self.path.exists(): raise WorkflowError("Offene Veröffentlichung: zuerst scripts/publish_bookkeeping.py resume ausführen")
            snapshot = os.environ.get("BOOKKEEPING_EXPECTED_SNAPSHOT")
            if snapshot and sha((self.repo / "buchhaltung/database.json.enc").read_bytes()) != snapshot:
                raise WorkflowError("Dashboard veraltet; neu erzeugen und den aktuellen Befehl verwenden")
            if self.names("diff", "--cached", "--name-only", "-z"):
                raise WorkflowError("Bereits vorgemerkte Git-Änderungen zuerst separat abschließen")
            # Unrelated source/user edits are allowed; archive/generator edits are not.
            scope = self.names("diff", "--name-only", "HEAD", "-z", "--", "buchhaltung", "dashboard.html", "bookkeeping_checklist.json.enc")
            scope += self.names("ls-files", "--others", "--exclude-standard", "-z", "--", "buchhaltung", "bookkeeping_checklist.json.enc")
            if scope: raise WorkflowError("Buchhaltung/Dashboard enthält offene Änderungen; vor neuer Buchung abschließen")
            self.check_code()
            base = git(self.repo, "rev-parse", "HEAD").decode().strip()
            git(self.repo, "symbolic-ref", "--short", "HEAD")
            git(self.repo, "rev-parse", "--abbrev-ref", "@{upstream}")
            self.state = {"version": 1, "token": uuid.uuid4().hex, "action": self.action,
                          "base": base, "before_digest": self.digest(), "phase": "writing", "mode": self.mode, "tool_commit": assert_tool_clean()}
            self.write(); return self
        except BaseException:
            self.lock.release(); raise

    def __exit__(self, typ, exc, traceback):
        if not self.enabled: return False
        try:
            if typ:
                proof_changes = self.proof_changes() if self.mode == "proofs" else []
                if not proof_changes and self.digest() == self.state["before_digest"] and not (self.repo / "output/local-invoice-transaction.enc").exists():
                    self.path.unlink()
                return False
            self.result = self.finish()
        finally:
            self.lock.release()
        return False

    def head(self):
        return git(self.repo, "rev-parse", "HEAD").decode().strip()

    def own_commit(self, message, parent):
        names = self.names("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD")
        allowed = (lambda n: n.startswith("buchhaltung/nachweise/")) if "proof update:" in message or "timestamp:" in message else (lambda n: data_path(n) or n in ("dashboard.html", "tool-version.json"))
        return (git(self.repo, "log", "-1", "--format=%s").decode().strip() == message
                and git(self.repo, "rev-parse", "HEAD^").decode().strip() == parent
                and all(allowed(n) for n in names))

    def commit_paths(self, names, message):
        staged = set(self.names("diff", "--cached", "--name-only", "-z"))
        if not staged <= set(names): raise WorkflowError("Fremde Git-Indexänderung; Veröffentlichung gestoppt")
        git(self.repo, "add", "--", *names)
        if set(self.names("diff", "--cached", "--name-only", "-z")) - set(names):
            raise WorkflowError("Git-Index enthält fremde Dateien")
        git(self.repo, "commit", "-m", message)
        return self.head()

    def proof_changes(self):
        names = self.names("diff", "--name-only", "HEAD", "-z", "--", "buchhaltung/nachweise")
        names += self.names("ls-files", "--others", "--exclude-standard", "-z", "--", "buchhaltung/nachweise")
        return sorted(set(names))

    def ensure_proof(self, statement):
        proof = Path(str(statement) + ".ots")
        if proof.exists():
            try:
                if not list(load_proof(statement, proof).timestamp.all_attestations()):
                    raise WorkflowError("Unvollständiger Kalendernachweis")
            except Exception:
                if self.names("ls-files", "--", proof.relative_to(self.repo).as_posix()):
                    raise WorkflowError("Bereits eingecheckter OTS-Nachweis ist ungültig; separat prüfen")
                proof.rename(self.repo / "output" / ("incomplete-ots-" + uuid.uuid4().hex + ".ots"))
        if not proof.exists(): self.stamp(statement, proof)
        if not list(load_proof(statement, proof).timestamp.all_attestations()):
            raise WorkflowError("OTS-Nachweis enthält keine Kalender-/Bitcoin-Attestierung")
        return proof

    def finish_proofs(self):
        state = self.state
        if self.digest() != state["before_digest"]: raise WorkflowError("Archiv während Nachweisaktualisierung verändert")
        names = self.proof_changes()
        message = "Bookkeeping proof update: " + state["token"]
        if self.head() != state["base"]:
            if not self.own_commit(message, state["base"]): raise WorkflowError("Fremder Commit vor Nachweis-Push")
            if names: raise WorkflowError("Nachweise nach dem Commit erneut verändert")
            state["proof_commit"] = self.head()
        elif not names:
            self.path.unlink(); return {"status": "unchanged", "new_commit": False}
        else:
            if any(not re.fullmatch(r"buchhaltung/nachweise/[a-f0-9]{40}(?:[a-f0-9]{24})?\.json(?:\.ots(?:\.bak)?)?", n) for n in names):
                raise WorkflowError("Unerwartete Datei im Zeitnachweis; nicht automatisch committen")
            for name in names:
                if name.endswith(".json"):
                    statement = self.repo / name
                    verify_checkpoint(self.repo, statement)
                    # A failed manual stamp may have written only the statement.
                    # Resume its exact commit; never publish a statement alone.
                    self.ensure_proof(statement)
            names = self.proof_changes()
            # A changed proof must still match the statement it certifies.
            for name in names:
                if name.endswith(".ots"):
                    if not list(load_proof(self.repo / name[:-4], self.repo / name).timestamp.all_attestations()):
                        raise WorkflowError("Zeitnachweis enthält keine Kalender-/Bitcoin-Attestierung")
            state["proof_commit"] = self.commit_paths(names, message)
        state["phase"] = "proof_push"; self.write()
        git(self.repo, "push")
        self.path.unlink(); return {"status": "proofs_published", "proof_commit": state["proof_commit"], "pushed": True}

    def stamp(self, statement, proof):
        subprocess.run([sys.executable, str(tool_root() / "scripts/ots_windows.py"), "stamp", str(statement)],
                       cwd=self.repo, capture_output=True, check=True, timeout=60)

    def finish(self):
        assert_data_repo(self.repo, remote=True)
        if assert_tool_clean() != self.state["tool_commit"]: raise WorkflowError("Toolversion während Veröffentlichung geändert")
        state = self.state
        if (self.repo / "output/local-invoice-transaction.enc").exists():
            raise WorkflowError("Unterbrochene Archivtransaktion: publish_bookkeeping.py resume ausführen")
        with FileLock(self.repo / "output/archive.lock", timeout=0): Archive(self.repo).verify()
        if state.get("mode") == "proofs": return self.finish_proofs()
        if state.get("after_digest") and self.digest() != state["after_digest"]:
            raise WorkflowError("Archiv wurde nach Beginn der Veröffentlichung verändert")
        if not state.get("data_commit"):
            message = "Bookkeeping: " + state["action"] + " [" + state["token"] + "]"
            if self.head() != state["base"]:
                if not self.own_commit(message, state["base"]): raise WorkflowError("Git-HEAD hat sich während der Veröffentlichung verändert")
                state["data_commit"] = self.head()
            elif self.digest() == state["before_digest"]:
                self.path.unlink(); return {"status": "unchanged", "new_commit": False}
            else:
                if state.get("after_digest") and self.digest() != state["after_digest"]:
                    raise WorkflowError("Archiv wurde nach unterbrochener Veröffentlichung verändert")
                atomic(self.repo / "tool-version.json", encoded({"version": 1, "git_commit": state["tool_commit"]}))
                state["after_digest"] = self.digest(); state["phase"] = "commit"; self.write()
                subprocess.run([sys.executable, "-X", "utf8", str(tool_root() / "scripts/build_bookkeeping_dashboard.py")],
                               cwd=self.repo, capture_output=True, check=True, timeout=60)
                changed = self.names("diff", "--name-only", "HEAD", "-z", "--", "buchhaltung", "bookkeeping_checklist.json.enc")
                changed += self.names("ls-files", "--others", "--exclude-standard", "-z", "--", "buchhaltung", "bookkeeping_checklist.json.enc")
                if not changed or any(not data_path(n) for n in changed): raise WorkflowError("Unerwartete Archivänderungen; keine fremden Dateien committen")
                state["data_commit"] = self.commit_paths(sorted(set(changed)) + ["dashboard.html", "tool-version.json"], message)
            state["phase"] = "data_push"; self.write()
        data_commit = state["data_commit"]
        if self.head() not in (data_commit, state.get("proof_commit")):
            message = "Bookkeeping timestamp: " + state["token"]
            if not self.own_commit(message, data_commit): raise WorkflowError("Fremder Commit vor OTS-Abschluss; Veröffentlichung gestoppt")
            state["proof_commit"] = self.head(); self.write()
        if not state.get("data_pushed"):
            git(self.repo, "push"); state["data_pushed"] = True; state["phase"] = "ots"; self.write()
        if not state.get("proof_commit"):
            with FileLock(self.repo / "output/archive.lock", timeout=0):
                Archive(self.repo).verify()
                statement = checkpoint(self.repo, data_commit)
                proof = self.ensure_proof(statement)
            names = [statement.relative_to(self.repo).as_posix(), proof.relative_to(self.repo).as_posix()]
            state["proof_commit"] = self.commit_paths(names, "Bookkeeping timestamp: " + state["token"])
            state["phase"] = "proof_push"; self.write()
        git(self.repo, "push")
        if self.names("diff", "--name-only", "HEAD", "-z", "--", "buchhaltung", "dashboard.html") or self.names("ls-files", "--others", "--exclude-standard", "-z", "--", "buchhaltung"):
            raise WorkflowError("Weitere Archivänderungen vorhanden; Abschluss prüfen")
        result = {"status": "published_ots_pending", "data_commit": data_commit,
                  "proof_commit": state["proof_commit"], "pushed": True, "ots_submitted": True,
                  "blockchain_verified": False, "confirm_command": ".venv\\Scripts\\python.exe -X utf8 scripts\\publish_bookkeeping.py confirm"}
        self.path.unlink(); return result


def resume(repo):
    publication = Publication(repo, "resume")
    with publication.lock:
        if not publication.path.exists(): return {"status": "nothing_pending"}
        publication.state = json.loads(publication.path.read_bytes())
        publication.mode = publication.state.get("mode", "data")
        publication.check_code()
        with FileLock(publication.repo / "output/archive.lock", timeout=0):
            workflow = LocalInvoices(Archive(publication.repo))
            if workflow.journal.exists(): workflow.recover()
        return publication.finish()
