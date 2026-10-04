import io
import json
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest
from opentimestamps.core.notary import PendingAttestation
from opentimestamps.core.op import OpSHA256
from opentimestamps.core.serialize import BytesSerializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile

from autobookkeeping.archive import Archive, checkpoint, sha, verify_checkpoint
from autobookkeeping.homeoffice import record
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError
from autobookkeeping import publication as module
from autobookkeeping.publication import Publication, resume

ROOT = Path(__file__).resolve().parents[1]
BUILD = runpy.run_path(str(ROOT / 'scripts/build_bookkeeping_dashboard.py'))


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    tool = tmp_path / 'tool'; tool.mkdir(); repo = tool / 'daten'; repo.mkdir()
    from autobookkeeping import workspace
    monkeypatch.setattr(workspace, 'TOOL_ROOT', tool)
    remote = tmp_path / 'remote.git'
    subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
    def git(*args): return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.PIPE).decode().strip()
    git('init'); git('config', 'user.name', 'Synthetic Test'); git('config', 'user.email', 'test@example.invalid')
    git('config', 'core.autocrlf', 'false')
    for name in BUILD['CODE']:
        target = tool / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / name, target)
    (repo / '.gitignore').write_text('.env\noutput/\n__pycache__/\n', encoding='utf8')
    (repo / '.env').write_text('ENCRYPTION_PASSWORD=synthetic-password\n', encoding='utf8')
    (repo / '.bookkeeping-data.json').write_text('{"version":1,"role":"data"}')
    (repo / 'workspace.json').write_text(json.dumps({'expected_push_url': str(remote)}))
    (tool / '.gitignore').write_text('/daten/\n__pycache__/\n')
    for args in [('init',), ('config','user.name','Synthetic Test'), ('config','user.email','test@example.invalid'), ('add','.'), ('commit','-m','Synthetic tool')]:
        subprocess.run(['git','-C',str(tool),*args],check=True,capture_output=True)
    archive = Archive(repo); archive.init(); BUILD['build'](repo, tool=tool)
    git('add', '.'); git('commit', '-m', 'Synthetic initial archive')
    git('remote', 'add', 'origin', str(remote)); git('push', '-u', 'origin', 'HEAD')
    def stamp(self, statement, proof):
        detached = DetachedTimestampFile.from_fd(OpSHA256(), io.BytesIO(statement.read_bytes()))
        detached.timestamp.attestations.add(PendingAttestation('https://calendar.example.invalid'))
        context = BytesSerializationContext(); detached.serialize(context); proof.write_bytes(context.getbytes())
    monkeypatch.setattr(Publication, 'stamp', stamp)
    monkeypatch.delenv('BOOKKEEPING_EXPECTED_SNAPSHOT', raising=False)
    return repo, archive, git


def save(repo, archive):
    with Publication(repo, 'homeoffice set') as publication:
        record(LocalInvoices(archive), 2026, 100, 'PRIVATE SYNTHETIC BASIS', True, True)
    return publication.result


def test_encrypted_checklist_changes_run_the_complete_private_pipeline(fixture):
    repo,archive,git=fixture
    from autobookkeeping.checklist import ChecklistStore
    with Publication(repo,'checklist update') as publication:
        ChecklistStore(repo/'bookkeeping_checklist.json.enc').upsert('SYNTHETIC-ORDER',{'note':'PRIVATE SYNTHETIC BUYER'})
    result=publication.result
    assert result['status']=='published_ots_pending'
    assert git('rev-parse','@{upstream}')==result['proof_commit']
    statement=repo/'buchhaltung/nachweise'/(result['data_commit']+'.json')
    assert 'bookkeeping_checklist.json.enc' in json.loads(statement.read_bytes())['files_sha256']
    assert verify_checkpoint(repo,statement)['git_integrity']


def assert_complete(repo, archive, git, result):
    assert result['status'] == 'published_ots_pending' and not result['blockchain_verified']
    assert git('rev-parse', '@{upstream}') == result['proof_commit'] == git('rev-parse', 'HEAD')
    assert git('rev-list', '--count', 'HEAD') == '3'
    statement = repo / 'buchhaltung/nachweise' / (result['data_commit'] + '.json')
    assert verify_checkpoint(repo, statement)['git_integrity']
    assert archive.catalog()['homeoffice_allowances']['2026']['current']['days'] == 100
    assert not (repo / 'output/publication.json').exists()
    assert 'PRIVATE SYNTHETIC BASIS' not in (repo / 'dashboard.html').read_text(encoding='utf8')
    assert '.env' not in git('ls-files')


def test_full_pipeline_preserves_unrelated_edits_and_is_idempotent(fixture):
    repo, archive, git = fixture
    (repo / 'user-notes.txt').write_text('Unrelated user work', encoding='utf8')
    assert_complete(repo, archive, git, save(repo, archive))
    assert git('status', '--short') == '?? user-notes.txt'
    assert save(repo, archive)['status'] == 'unchanged'
    assert git('rev-list', '--count', 'HEAD') == '3'


@pytest.mark.parametrize('push_number', [1, 2])
def test_push_failure_resumes_without_rebooking(fixture, monkeypatch, push_number):
    repo, archive, git = fixture; original = module.git; pushes = 0
    def fail(repo, *args):
        nonlocal pushes
        if args[0] == 'push':
            pushes += 1
            if pushes == push_number: raise OSError('Synthetic network failure')
        return original(repo, *args)
    monkeypatch.setattr(module, 'git', fail)
    with pytest.raises(OSError): save(repo, archive)
    assert (repo / 'output/publication.json').exists()
    assert len(archive.catalog()['homeoffice_allowances']['2026']['history']) == 0
    monkeypatch.setattr(module, 'git', original)
    assert_complete(repo, archive, git, resume(repo))


def test_calendar_failure_resumes_exact_data_commit(fixture, monkeypatch):
    repo, archive, git = fixture; stamp = Publication.stamp
    monkeypatch.setattr(Publication, 'stamp', lambda *args: (_ for _ in ()).throw(OSError('Calendar offline')))
    with pytest.raises(OSError): save(repo, archive)
    data_commit = git('rev-parse', 'HEAD')
    monkeypatch.setattr(Publication, 'stamp', stamp)
    result = resume(repo)
    assert result['data_commit'] == data_commit
    assert_complete(repo, archive, git, result)


@pytest.mark.parametrize('phase', ['data_push', 'proof_push'])
def test_crash_after_commit_adopts_existing_commit(fixture, monkeypatch, phase):
    repo, archive, git = fixture; write = Publication.write; raised = False
    def crash(self):
        nonlocal raised
        if self.state['phase'] == phase and not raised:
            raised = True; raise OSError('Power loss after Git commit')
        write(self)
    monkeypatch.setattr(Publication, 'write', crash)
    with pytest.raises(OSError): save(repo, archive)
    monkeypatch.setattr(Publication, 'write', write)
    assert_complete(repo, archive, git, resume(repo))


@pytest.mark.parametrize('obstacle', ['staged', 'archive', 'code', 'snapshot'])
def test_preflight_blocks_before_mutation(fixture, monkeypatch, obstacle):
    repo, archive, git = fixture; before = archive.catalog()
    if obstacle == 'staged':
        (repo / 'foreign.txt').write_text('Foreign'); git('add', 'foreign.txt')
    elif obstacle == 'archive': (repo / 'buchhaltung/foreign.pdf').write_bytes(b'Unencrypted')
    elif obstacle == 'code':
        with (repo.parent / 'scripts/homeoffice.py').open('a', encoding='utf8') as f: f.write('\n# Foreign edit\n')
    else: monkeypatch.setenv('BOOKKEEPING_EXPECTED_SNAPSHOT', '0' * 64)
    with pytest.raises(WorkflowError): save(repo, archive)
    assert archive.catalog() == before and not (repo / 'output/publication.json').exists()


def test_changed_archive_blocks_resume(fixture, monkeypatch):
    repo, archive, git = fixture; original = module.git
    def fail(repo, *args):
        if args[0] == 'push': raise OSError('Offline')
        return original(repo, *args)
    monkeypatch.setattr(module, 'git', fail)
    with pytest.raises(OSError): save(repo, archive)
    record(LocalInvoices(archive), 2026, 101, 'Foreign change', True, True)
    monkeypatch.setattr(module, 'git', original)
    with pytest.raises(WorkflowError, match='verändert'): resume(repo)


def test_mutation_error_clears_empty_publication(fixture):
    repo, archive, git = fixture
    with pytest.raises(WorkflowError):
        with Publication(repo, 'homeoffice set'):
            record(LocalInvoices(archive), 2026, 100, 'Basis', True, False)
    assert not (repo / 'output/publication.json').exists()


def test_proof_only_update_is_committed_without_recursive_stamp(fixture):
    repo, archive, git = fixture; result = save(repo, archive)
    statement = repo / 'buchhaltung/nachweise' / (result['data_commit'] + '.json')
    before = sha((archive.root / 'database.json.enc').read_bytes())
    with Publication(repo, 'proof update', mode='proofs') as publication:
        proof = Path(str(statement) + '.ots')
        Path(str(proof) + '.bak').write_bytes(proof.read_bytes())
    assert publication.result['status'] == 'proofs_published'
    assert git('rev-list', '--count', 'HEAD') == '4'
    assert git('rev-parse', '@{upstream}') == git('rev-parse', 'HEAD')
    assert sha((archive.root / 'database.json.enc').read_bytes()) == before


def test_encrypted_journal_recovery_then_publication(fixture, monkeypatch):
    repo, archive, git = fixture; original = archive.save_catalog
    monkeypatch.setattr(archive, 'save_catalog', lambda *args: (_ for _ in ()).throw(OSError('Power loss while saving')))
    with pytest.raises(OSError): save(repo, archive)
    assert (repo / 'output/local-invoice-transaction.enc').exists()
    monkeypatch.setattr(archive, 'save_catalog', original)
    assert_complete(repo, archive, git, resume(repo))


def test_hook_can_reacquire_archive_lock(fixture):
    # The real hook acquires the archive lock; publication must release it before Git.
    import sys
    repo, archive, git = fixture
    hook = repo / '.git/hooks/pre-commit'
    executable = Path(sys.executable).as_posix()
    hook.write_bytes((f"#!/bin/sh\nexec '{executable}' -X utf8 {(repo.parent / 'scripts/build_bookkeeping_dashboard.py').as_posix()} --staged\n").encode('utf8'))
    assert_complete(repo, archive, git, save(repo, archive))


def test_manual_stamp_failure_cannot_publish_statement_without_proof(fixture, monkeypatch):
    repo, archive, git = fixture; base = git('rev-parse', 'HEAD')
    with pytest.raises(OSError):
        with Publication(repo, 'archive stamp', mode='proofs'):
            statement = checkpoint(repo, base)
            raise OSError('Calendar offline before proof was written')
    result = resume(repo)
    assert result['status'] == 'proofs_published'
    assert Path(str(statement) + '.ots').is_file()
    assert git('rev-list', '--count', 'HEAD') == '2'
    assert git('rev-parse', '@{upstream}') == git('rev-parse', 'HEAD')
