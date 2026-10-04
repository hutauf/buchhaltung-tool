"""Exercise independent repositories, publication guards and migrated history."""
import json
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest
from autobookkeeping import workspace
from autobookkeeping.archive import Archive, atomic, cd_export, checkpoint, encoded, outside, seal, verify_checkpoint
from autobookkeeping.checklist import ChecklistStore
from autobookkeeping.local_invoices import WorkflowError

SOURCE=Path(__file__).resolve().parents[1]


def raw(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.PIPE).decode().strip()


def initialize(repo):
    repo.mkdir(parents=True)
    raw(repo,'init','-b','main');raw(repo,'config','user.name','Synthetic')
    raw(repo,'config','user.email','test@example.invalid');raw(repo,'config','core.autocrlf','false')


@pytest.fixture
def split(tmp_path,monkeypatch):
    tool=tmp_path/'tool';initialize(tool)
    monkeypatch.setattr(workspace,'TOOL_ROOT',tool)
    (tool/'.gitignore').write_text('/daten/\n')
    (tool/'.bookkeeping-tool.json').write_bytes(encoded({'role':'tool'}))
    raw(tool,'add','.');raw(tool,'commit','-m','Synthetic tools')
    data=tool/'daten';initialize(data)
    (data/'.bookkeeping-data.json').write_bytes(encoded({'role':'data'}))
    (data/'.gitignore').write_text('.env\noutput/\n')
    (data/'.gitattributes').write_text('buchhaltung/** -text\nmigration/** -text\n/*.json -text\n*.enc -text\n')
    (data/'state.txt').write_text('Synthetic data')
    (data/'.env').write_text('ENCRYPTION_PASSWORD=synthetic-password\n')
    remote=tmp_path/'private.git'
    subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
    (data/'workspace.json').write_bytes(encoded({'expected_push_url':str(remote)}))
    raw(data,'add','.');raw(data,'commit','-m','Synthetic data')
    raw(data,'remote','add','origin',str(remote));raw(data,'push','-u','origin','main')
    return tool,data,remote


def test_missing_inner_git_cannot_fall_back_to_outer(split):
    tool,data,_=split
    (data/'.git').rename(data/'hidden-git')
    before=raw(tool,'rev-parse','HEAD')
    with pytest.raises(WorkflowError):workspace.data_root()
    assert raw(tool,'rev-parse','HEAD')==before


def test_tool_is_never_accepted_as_bookkeeping_repo(split):
    tool,_,_=split
    (tool/'.bookkeeping-data.json').write_bytes(encoded({'role':'data'}))
    with pytest.raises(WorkflowError):workspace.assert_data_repo(tool)


def test_git_hook_environment_cannot_redirect_operations(split,monkeypatch):
    tool,data,_=split
    monkeypatch.setenv('GIT_DIR',str(tool/'.git'))
    monkeypatch.setenv('GIT_WORK_TREE',str(tool))
    assert workspace.assert_data_repo(data)==data.resolve()
    assert workspace.git(data,'log','-1','--format=%s').decode().strip()=='Synthetic data'


def test_outer_add_ignores_entire_private_repo(split):
    tool,data,_=split
    (data/'person.pdf').write_bytes(b'PRIVATE SYNTHETIC CONTENT')
    raw(tool,'add','.')
    assert raw(tool,'diff','--cached','--name-only')==''
    assert not any(n.startswith('daten') for n in raw(tool,'ls-files').splitlines())


def test_outer_commit_guard_blocks_without_creating_a_commit(split):
    tool,_,_=split
    shutil.copytree(SOURCE/'.githooks',tool/'.githooks')
    raw(tool,'config','core.hooksPath','.githooks')
    before=raw(tool,'rev-parse','HEAD')
    result=subprocess.run(['git','-C',str(tool),'commit','--allow-empty','-m','Should be blocked'],capture_output=True)
    assert result.returncode!=0 and raw(tool,'rev-parse','HEAD')==before


@pytest.mark.parametrize('change',['different','additional','public'])
def test_wrong_or_multiple_push_destinations_are_rejected(split,change):
    tool,data,remote=split
    assert workspace.assert_data_repo(data,remote=True)==data.resolve()
    if change=='different':raw(data,'remote','set-url','--push','origin',str(remote)+'-other')
    elif change=='additional':
        raw(data,'remote','set-url','--add','--push','origin',str(remote))
        raw(data,'remote','set-url','--add','--push','origin',str(remote)+'-other')
    else:raw(tool,'remote','add','origin',str(remote))
    with pytest.raises(WorkflowError):workspace.assert_data_repo(data,remote=True)


def test_plaintext_exports_cannot_enter_either_repo(split,tmp_path):
    tool,data,_=split
    for target in (data/'export.pdf',tool/'export.pdf'):
        with pytest.raises(ValueError):outside(data,target)
    assert outside(data,tmp_path/'export.pdf')==tmp_path/'export.pdf'


def test_operational_checklist_is_encrypted_and_readable(split):
    _,data,_=split
    archive=Archive(data);archive.init()
    store=ChecklistStore(data/'bookkeeping_checklist.json.enc')
    store.upsert('SYNTHETIC-ORDER',{'note':'PRIVATE SYNTHETIC BUYER'})
    assert store.find('SYNTHETIC-ORDER')['note']=='PRIVATE SYNTHETIC BUYER'
    cipher=store.path.read_bytes()
    assert b'PRIVATE SYNTHETIC BUYER' not in cipher and b'SYNTHETIC-ORDER' not in cipher


def test_legacy_timestamp_verifies_without_original_checkout(split,tmp_path):
    _,data,_=split
    legacy=tmp_path/'legacy';initialize(legacy)
    old=Archive(legacy,'synthetic-password');old.init()
    raw(legacy,'add','.');raw(legacy,'commit','-m','Synthetic legacy archive')
    statement=checkpoint(legacy)
    current=Archive(data);current.init()
    bundle=tmp_path/'legacy.bundle';raw(legacy,'bundle','create',str(bundle),'--all')
    atomic(data/'migration/legacy-repository.bundle.enc',seal(current.unlock(),bundle.read_bytes(),'migration/legacy-repository.bundle'))
    destination=data/'buchhaltung/nachweise'/statement.name;atomic(destination,statement.read_bytes())
    legacy.rename(tmp_path/'unavailable-legacy')
    assert verify_checkpoint(data,destination)['git_integrity']


def test_cd_restores_both_repo_histories(split,tmp_path):
    tool,data,_=split
    for directory in ('src','scripts','skills'):
        shutil.copytree(SOURCE/directory,tool/directory,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(SOURCE/'pyproject.toml',tool/'pyproject.toml')
    raw(tool,'add','.');raw(tool,'commit','-m','Synthetic backup tools')
    archive=Archive(data);archive.init()
    atomic(data/'dashboard.html',b'<!doctype html><title>Synthetic</title>')
    raw(data,'add','.');raw(data,'commit','-m','Synthetic archive')
    source=tmp_path/'cd';cd_export(archive,source)
    restore=runpy.run_path(str(SOURCE/'scripts/restore_backup.py'))['restore']
    bundle=restore(source,data/'.env',tmp_path/'restored-bundle')['bundle']
    clone=tmp_path/'restored-tool'
    subprocess.run(['git','clone',str(source/'tool.bundle'),str(clone)],check=True,capture_output=True)
    subprocess.run(['git','clone',bundle,str(clone/'daten')],check=True,capture_output=True)
    assert raw(clone,'rev-parse','HEAD')==raw(tool,'rev-parse','HEAD')
    assert raw(clone/'daten','rev-parse','HEAD')==raw(data,'rev-parse','HEAD')
    assert Archive(clone/'daten','synthetic-password').verify()['ok']
    assert verify_checkpoint(clone/'daten',checkpoint(clone/'daten'))['git_integrity']
