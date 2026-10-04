"""Regression checks: private data in previous commits must block a push."""
import subprocess
from pathlib import Path
import pytest
from autobookkeeping.public_privacy import audit,content_issues

NAME='Hut auf'
EMAIL='synthetic@users.noreply.github.com'


def git(repo,*args):return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.PIPE).decode().strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path,'init','-b','main');git(tmp_path,'config','user.name',NAME);git(tmp_path,'config','user.email',EMAIL)
    (tmp_path/'README.md').write_text('Synthetic public code\n')
    git(tmp_path,'add','.');git(tmp_path,'commit','-m','Synthetic initial code')
    return tmp_path


def test_valid_code_and_identity_pass(repo):
    assert audit(repo,NAME,EMAIL,fingerprints=set())['ok']


def test_old_private_content_is_detected_after_current_file_is_clean(repo):
    (repo/'README.md').write_text('SYNTHETIC SENSITIVE VALUE\n');git(repo,'add','.');git(repo,'commit','-m','Synthetic test record')
    (repo/'README.md').write_text('Public code again\n');git(repo,'add','.');git(repo,'commit','-m','Synthetic clean state')
    result=audit(repo,NAME,EMAIL,fingerprints={'synthetic sensitive value'})
    assert not result['ok'] and any(i['reason']=='private_fingerprint' for i in result['issues'])
    assert 'SYNTHETIC SENSITIVE VALUE' not in str(result)


@pytest.mark.parametrize('filename',['receipt.pdf','timestamp.ots','database.json.enc','daten/private.py','dashboard.html'])
def test_non_code_and_private_locations_are_blocked(repo,filename):
    path=repo/filename;path.parent.mkdir(exist_ok=True);path.write_bytes(b'SYNTHETIC')
    git(repo,'add','.');git(repo,'commit','-m','Synthetic forbidden file')
    assert not audit(repo,NAME,EMAIL,fingerprints=set())['ok']


def test_private_author_identity_is_blocked(repo):
    git(repo,'config','user.name','SYNTHETIC PRIVATE AUTHOR')
    git(repo,'commit','--allow-empty','-m','Synthetic identity test')
    assert any(i['reason']=='unexpected_identity' for i in audit(repo,NAME,EMAIL,fingerprints=set())['issues'])


def test_direct_push_of_unreferenced_private_commit_is_checked(repo):
    old=git(repo,'rev-parse','HEAD');tree=git(repo,'rev-parse','HEAD^{tree}')
    git(repo,'config','user.name','SYNTHETIC PRIVATE AUTHOR')
    bad=git(repo,'commit-tree',tree,'-m','Synthetic unreferenced commit')
    assert audit(repo,NAME,EMAIL,fingerprints=set())['ok']
    assert not audit(repo,NAME,EMAIL,extra=(bad,),fingerprints=set())['ok']
    assert git(repo,'rev-parse','HEAD')==old


def test_personal_paths_and_orders_and_secret_substrings_are_blocked():
    path='/'.join(('C:','Users','SYNTHETIC_USER','file.txt')).encode()
    assert 'personal_path' in content_issues(path,set())
    order='-'.join(('99','99999','99999')).encode()
    assert 'non_synthetic_order_id' in content_issues(order,set())
    assert not content_issues(b'00-00000-00001',set())
    assert 'private_fingerprint' in content_issues(b'prefix-SYNTHETIC-SECRET-suffix',set(),['synthetic-secret'])


def test_word_matching_does_not_confuse_names_with_code_substrings():
    assert not content_issues(b'character',{'char'})
    assert 'private_fingerprint' in content_issues(b'CHAR',{'char'})


def test_anonymous_private_dashboard_snapshot_is_also_blocked(repo):
    from autobookkeeping.archive import Archive,sha
    data=repo/'daten';data.mkdir()
    git(data,'init','-b','main');git(data,'config','user.name',NAME);git(data,'config','user.email',EMAIL)
    (data/'.bookkeeping-data.json').write_text('{"role":"data"}')
    (data/'.env').write_text('ENCRYPTION_PASSWORD=SYNTHETIC-PRIVATE-PASSWORD\n')
    (data/'.gitignore').write_text('.env\n')
    archive=Archive(data);archive.init();git(data,'add','.');git(data,'commit','-m','Synthetic data')
    (repo/'.gitignore').write_text('/daten/\n');docs=repo/'docs';docs.mkdir()
    (docs/'snapshot.html').write_text('<script>{"source_sha256":"'+sha((archive.root/'database.json.enc').read_bytes())+'"}</script>')
    git(repo,'add','.');git(repo,'commit','-m','Synthetic anonymous snapshot')
    result=audit(repo,NAME,EMAIL)
    assert not result['ok'] and any(i.get('path')=='docs/snapshot.html' and i['reason']=='private_fingerprint' for i in result['issues'])
