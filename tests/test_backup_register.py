import json
import shutil
from pathlib import Path
import pytest
from autobookkeeping.archive import Archive, atomic, encoded, sha
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError
from autobookkeeping.backups import register, confirm, public_status, source_for, restore_test


def source(tmp_path):
    folder=tmp_path/'outside-export';folder.mkdir()
    descriptor={'version':1,'prepared_at':'2011-10-03T12:00:00+00:00','data_commit':'a'*40,'tool_commit':'b'*40}
    atomic(folder/'BACKUP.json',encoded(descriptor));atomic(folder/'payload.enc',b'SYNTHETIC ENCRYPTED PLACEHOLDER')
    atomic(folder/'SHA256SUMS.json',encoded({p.name:sha(p.read_bytes()) for p in folder.iterdir()}))
    return folder


def test_export_is_not_written_confirmation_requires_actual_readback_and_approval(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();archive=Archive(repo,'synthetic-password');archive.init();workflow=LocalInvoices(archive)
    export=source(tmp_path);result=register(workflow,export);bid=result['id']
    assert result['written'] is False and register(workflow,export)['changed'] is False
    medium=tmp_path/'medium';shutil.copytree(export,medium)
    with pytest.raises(WorkflowError):confirm(workflow,bid,medium,'PRIVATE LABEL',True,False)
    with pytest.raises(WorkflowError):confirm(workflow,bid,export,'PRIVATE LABEL',True,True)
    assert confirm(workflow,bid,medium,'PRIVATE LABEL',True,True)['readback_verified']
    status=public_status(archive.catalog());assert status['rows'][0]['readback_at']
    assert 'PRIVATE' not in str(status) and str(medium) not in str(status)
    (medium/'payload.enc').write_bytes(b'CORRUPTION')
    with pytest.raises(ValueError):source_for(workflow,bid,medium)
    assert archive.verify()['ok']


def test_failed_restore_is_recorded_without_false_success(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();archive=Archive(repo,'synthetic-password');archive.init();workflow=LocalInvoices(archive)
    folder=source(tmp_path);bid=register(workflow,folder)['id']
    result=restore_test(workflow,bid,folder)
    assert not result['ok'] and public_status(archive.catalog())['rows'][0]['restore_result']=='failed'
    assert archive.verify()['ok']


@pytest.mark.parametrize('legacy',[False,True])
def test_restore_clones_both_bundles_and_checks_exact_snapshot(tmp_path,legacy):
    import subprocess
    from autobookkeeping.archive import seal, checkpoint
    password='synthetic-\u00e4${SYNTHETIC_UNSET_VAR}' if legacy else 'synthetic-password'
    repo=tmp_path/'repo';repo.mkdir();archive=Archive(repo,password);archive.init()
    tool=tmp_path/'tool';tool.mkdir();(tool/'README.md').write_text('Synthetic tool')
    def git(directory,*args):return subprocess.check_output(['git','-C',str(directory),*args],stderr=subprocess.PIPE)
    if legacy:
        old=tmp_path/'legacy';old.mkdir();Archive(old,password).init()
        git(old,'init');git(old,'config','core.autocrlf','false');git(old,'config','user.name','Synthetic Test');git(old,'config','user.email','test@example.invalid')
        git(old,'add','.');git(old,'commit','-m','Synthetic legacy snapshot')
        statement=checkpoint(old)
        atomic(archive.root/'nachweise'/statement.name,statement.read_bytes())
        old_bundle=tmp_path/'legacy.bundle';git(old,'bundle','create',str(old_bundle),'--all')
        atomic(repo/'migration/legacy-repository.bundle.enc',seal(archive.unlock(),old_bundle.read_bytes(),'migration/legacy-repository.bundle'))
    for directory in (repo,tool):
        git(directory,'init');git(directory,'config','core.autocrlf','false');git(directory,'config','user.name','Synthetic Test');git(directory,'config','user.email','test@example.invalid')
        git(directory,'add','.');git(directory,'commit','-m','Synthetic snapshot')
    folder=tmp_path/'backup';folder.mkdir()
    bundle=tmp_path/'data.bundle';git(repo,'bundle','create',str(bundle),'--all')
    atomic(folder/'repository.bundle.enc',seal(archive.unlock(),bundle.read_bytes(),'repository.bundle'))
    git(tool,'bundle','create',str(folder/'tool.bundle'),'--all')
    atomic(folder/'BACKUP.json',encoded({'version':1,'prepared_at':'2011-10-03T12:00:00+00:00',
           'data_commit':git(repo,'rev-parse','HEAD').decode().strip(),'tool_commit':git(tool,'rev-parse','HEAD').decode().strip()}))
    atomic(folder/'SHA256SUMS.json',encoded({p.name:sha(p.read_bytes()) for p in folder.iterdir()}))
    workflow=LocalInvoices(archive);bid=register(workflow,folder)['id']
    result=restore_test(workflow,bid,folder,raise_failure=True)
    assert result['ok'],result
    assert result['restored'] and result['records']==0
    assert archive.catalog()['backup_register'][bid]['events'][-1]['git_proofs']==int(legacy)
    assert public_status(archive.catalog())['rows'][0]['restore_result']=='passed'
