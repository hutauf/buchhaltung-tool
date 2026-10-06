import copy
import json

from autobookkeeping.archive import Archive, encoded, sha
from autobookkeeping.retention import report
from test_archive import fixture_document


def test_complete_export_includes_history_drafts_evidence_cash_and_settings(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();archive=Archive(repo,'test-password')
    _,meta,pdf=fixture_document(tmp_path);archive.import_local(meta,[pdf])
    metadata=tmp_path/'evidence.json';metadata.write_bytes(encoded({'date':'2012-01-01','description':'SYNTHETIC PAYMENT EVIDENCE','verification_basis':'Synthetic source checked'}))
    evidence=tmp_path/'statement.csv';evidence.write_bytes(b'SYNTHETIC SOURCE;13.00\n')
    result=archive.import_evidence(evidence,metadata)
    assert result['booked'] is False and not archive.import_evidence(evidence,metadata)['changed']
    catalog=archive.catalog()
    original=copy.deepcopy(catalog['records']['imported:invoice:1']['current'])
    catalog['records']['imported:invoice:1']['history'].append(original)
    from autobookkeeping.homeoffice import calculate
    catalog['homeoffice_allowances']={'2023':{'current':dict(calculate(2023,210),eligibility_confirmed=True,basis='SYNTHETIC DAYS'),
                                            'history':[dict(calculate(2023,200),eligibility_confirmed=True,basis='SYNTHETIC OLD DAYS')]}}
    catalog['cash_events']={'test-payment':{'record_id':'imported:invoice:1','date':'2012-01-01','amount':'119.00','bucket':'income'}}
    catalog['cash_source_overrides']={'imported:invoice:1':{'complete':True}}
    catalog['cash_event_voids']={'test-payment':{'reason':'SYNTHETIC CORRECTION','at':'2012-01-02'}}
    draft_doc='2012/Rechnungen/synthetic-draft.pdf.enc';archive.write(draft_doc,pdf.read_bytes())
    catalog['documents'][draft_doc]={'sha256_plaintext':sha(pdf.read_bytes()),'bytes_plaintext':len(pdf.read_bytes()),'record_id':'test-draft'}
    catalog['local_invoice_drafts']={'test-draft':{'current':{'status':'test_draft','number':None,'documents':[draft_doc]},'history':[]}}
    catalog['local_invoice_settings']={'synthetic':True}
    archive.save_catalog(catalog)
    target=tmp_path/'export';result=archive.export(target,year='2011')
    assert result['complete'] and result['documents']==3
    assert json.loads((target/'catalog.json').read_bytes())==catalog
    assert json.loads((target/'export-manifest.json').read_bytes())['scope']=='complete'
    assert next((target/'2012').rglob('*.csv')).read_bytes()==evidence.read_bytes()
    assert len(archive.catalog()['records'])==1
    assert not list(target.rglob('.env'))


def test_retention_eleven_full_years_payment_extends_and_never_deletes():
    name='2011/Rechnungen/synthetic.pdf.enc'
    catalog={'documents':{name:{}},'records':{'r':{'current':{'id':'r','date':'2011-12-31','documents':[name]},'history':[]}}}
    assert not report(catalog,'2022-12-31')['documents'][0]['review_possible']
    assert report(catalog,'2023-01-01')['documents'][0]['review_possible']
    catalog['cash_events']={'c':{'record_id':'r','date':'2012-01-01'}}
    row=report(catalog,'2023-01-01')['documents'][0]
    assert row['earliest_review']=='2024-01-01' and not row['review_possible']
    assert not row['deletion_authorized'] and not report(catalog)['automatic_deletion']
    catalog['cash_event_voids']={'c':{'at':'2013-01-01'}}
    assert report(catalog,'2024-01-01')['documents'][0]['earliest_review']=='2025-01-01'
    unknown={'documents':{'unknown.enc':{}},'records':{}}
    assert report(unknown,'2099-01-01')['documents'][0]['earliest_review'] is None
