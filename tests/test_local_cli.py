"""Local entry point and offline handover must need no bookkeeping service."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from autobookkeeping import cli
from autobookkeeping.archive import encoded
from autobookkeeping.handover import read_handover
from autobookkeeping.local_invoices import WorkflowError


@pytest.mark.parametrize('argv,script,arguments',[
    (['rechnung','list'],'local_invoice.py',['list']),
    (['beleg','inspect','C:/Downloads/synthetic receipt.pdf'],'receipt.py',['inspect','C:/Downloads/synthetic receipt.pdf']),
    (['zahlung','erfassen','--metadata','synthetic.json','--approved'],'local_invoice.py',['cash-record','--metadata','synthetic.json','--approved']),
    (['zahlung','berichtigen','synthetic-id','--reason','Synthetic mistake','--approved'],'local_invoice.py',['cash-void','synthetic-id','--reason','Synthetic mistake','--approved']),
    (['pruefen'],'bookkeeping_archive.py',['verify']),
    (['sicherung','export','--output','outside'],'bookkeeping_archive.py',['cd-export','--output','outside']),
    (['sicherung','pruefen','outside'],'bookkeeping_archive.py',['cd-verify','outside']),
    (['sicherung','wiederherstellen','outside'],'restore_backup.py',['outside']),
    (['veroeffentlichen','resume'],'publish_bookkeeping.py',['resume']),
])
def test_routes_preserve_arguments_and_private_helpers(argv,script,arguments,monkeypatch):
    called=[]
    def run(command,**kwargs):
        called.append((command,kwargs));return SimpleNamespace(returncode=7)
    monkeypatch.setattr(cli.subprocess,'run',run)
    assert cli.main(argv)==7
    command,options=called[0]
    assert command[:3]==[sys.executable,'-X','utf8'] and Path(command[3]).name==script
    assert command[4:]==arguments
    assert options['cwd']==Path(cli.__file__).resolve().parents[2]


def test_payment_group_cannot_dispatch_other_invoice_actions():
    with pytest.raises(SystemExit):cli.main(['zahlung','issue','synthetic-id'])


@pytest.mark.parametrize('group',['rechnung','beleg','archiv','pruefen','dashboard','homeoffice','veroeffentlichen','zahlung','sicherung'])
def test_help_in_a_clean_checkout_without_data(tmp_path,group):
    source=Path(__file__).resolve().parents[1];tool=tmp_path/'tool'
    shutil.copytree(source/'src',tool/'src');shutil.copytree(source/'scripts',tool/'scripts')
    result=subprocess.run([sys.executable,'-X','utf8','-m','autobookkeeping.cli',group,'--help'],
                          cwd=tool,env={**os.environ,'PYTHONPATH':str(tool/'src')},capture_output=True)
    assert result.returncode==0,result.stderr.decode('utf8')
    assert not (tool/'daten').exists()


def report():
    return {'version':1,'last_number':'0900','inventory_complete':True,'unfinalized':0,
            'external_numbering_stopped':True,'verification_basis':'Synthetic full inventory and handover review'}


@pytest.mark.parametrize('change',[{'inventory_complete':False},{'unfinalized':1},{'unfinalized':False},
    {'external_numbering_stopped':False},{'verification_basis':''},{'last_number':'BAD'}])
def test_incomplete_offline_handover_is_rejected(tmp_path,change):
    repo=tmp_path/'repo';repo.mkdir();path=tmp_path/'handover.json';path.write_bytes(encoded({**report(),**change}))
    with pytest.raises(WorkflowError):read_handover(repo,path)


def test_handover_digest_and_plaintext_boundary(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();path=tmp_path/'handover.json';path.write_bytes(encoded(report()))
    value,reference=read_handover(repo,path)
    assert value['last_number']=='0900' and reference['source_sha256']
    private=repo/'handover.json';private.write_bytes(path.read_bytes())
    with pytest.raises(ValueError):read_handover(repo,private)
