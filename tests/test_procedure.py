import copy
import json
import pytest
from autobookkeeping.archive import Archive, sha
from autobookkeeping.local_invoices import LocalInvoices
from autobookkeeping.procedure import prepare, save, public_status, markdown, interview_prompt


def test_private_operating_description_review_revision_encryption_and_history(tmp_path):
    root=tmp_path/'repo';root.mkdir();archive=Archive(root,'synthetic-password');archive.init()
    answers={'responsibility':{'status':'documented','text':'PRIVATE RESPONSIBLE PERSON'},
             'backup':{'status':'open','text':'No independent backup yet'}}
    draft=prepare(archive,answers,'2011-01-01',tmp_path/'proposal')
    assert not public_status(archive.catalog())['available']
    body=json.loads((tmp_path/'proposal/betriebsangaben.json').read_bytes())
    with pytest.raises(ValueError):save(LocalInvoices(archive),body,draft['revision'],False)
    altered=copy.deepcopy(body);altered['answers']['responsibility']['text']='changed'
    with pytest.raises(ValueError):save(LocalInvoices(archive),altered,draft['revision'],True)
    save(LocalInvoices(archive),body,draft['revision'],True)
    assert public_status(archive.catalog())['documented']==1 and public_status(archive.catalog())['open']==11
    assert 'PRIVATE' not in json.dumps(public_status(archive.catalog()))
    assert b'PRIVATE RESPONSIBLE' not in (archive.root/'database.json.enc').read_bytes()
    second=prepare(archive,{'backup':{'status':'documented','text':'Synthetic external drive'}},'2011-01-02',tmp_path/'second')
    save(LocalInvoices(archive),json.loads((tmp_path/'second/betriebsangaben.json').read_bytes()),second['revision'],True)
    current=archive.catalog()['operating_procedure']
    assert len(current['history'])==1 and 'PRIVATE RESPONSIBLE' in markdown(current['current'])
    with pytest.raises(ValueError):save(LocalInvoices(archive),body,draft['revision'],True)
    with pytest.raises(ValueError):prepare(archive,{},'2011-01-01',root/'plaintext')
    assert archive.verify()['ok']
    archive.export(tmp_path/'complete-export')
    assert 'Synthetic external drive' in (tmp_path/'complete-export/dokumentation/betriebsangaben.md').read_text(encoding='utf8')
    assert 'No independent backup yet' in (tmp_path/'complete-export/dokumentation/betriebsangaben-historie/0001.md').read_text(encoding='utf8')
    assert 'keine Betriebsprüfung' in interview_prompt()


def test_unknown_fields_and_unexplained_nonapplicability_are_rejected(tmp_path):
    from autobookkeeping.procedure import proposal
    for answers in ({'unexpected':{'status':'open','text':''}},
                    {'backup':{'status':'not_applicable','text':''}},
                    {'backup':{'status':'documented','text':'','secret':'never'}}):
        with pytest.raises(ValueError):proposal({},answers,'2011-01-01')
