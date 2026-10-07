import copy
from pathlib import Path
import pytest
from test_receipts import setup, meta, pdf, prepare, book
from autobookkeeping.archive import encoded
from autobookkeeping.cashflow import document_flows, record_cash, void_cash
from autobookkeeping.dashboard import projection
from autobookkeeping.local_invoices import WorkflowError
from autobookkeeping.ledger_validation import validate


def credit(receipts,tmp_path,original,**overrides):
    metadata=meta(number='SYNTHETIC-CREDIT',gross='5.95',net='5.00',vat='.95',
                  document_type='supplier_credit',original_id=original,correction_reason='Synthetic returned goods')
    metadata.update(overrides)
    review=receipts.inspect(pdf(tmp_path/(metadata['number']+'.pdf'),metadata['number']),tmp_path/(metadata['number']+'-review'))
    return prepare(receipts,review,metadata)


def test_supplier_credit_original_and_approval_preserved_until_actual_refund(setup,tmp_path):
    archive,workflow,receipts,source,review=setup
    original=book(receipts,prepare(receipts,review,meta()))['record_id']
    before=copy.deepcopy(archive.catalog()['records'][original])
    draft=credit(receipts,tmp_path,original)
    with pytest.raises(WorkflowError):receipts.book(draft['id'],draft['revision'],False)
    result=book(receipts,draft); catalog=archive.catalog(); row=catalog['records'][result['record_id']]['current']
    assert row['gross']=='-5.95' and row['source_record']['gross']=='5.95'
    assert catalog['records'][original]==before and document_flows(catalog,row)[0]==[]
    assert book(receipts,draft)['changed'] is False
    assert archive.verify()['ok']
    event=record_cash(workflow,{'record_id':row['id'],'amount':'5.00','date':'2011-10-05',
                              'external_reference':'SYNTHETIC-REFUND','evidence':'Synthetic bank entry', 'source_complete':True},True)
    public=next(r for r in projection(archive.catalog(),'0'*64)['rows'] if r['kind']=='expense_credit')
    assert public['flows'][0]['amount_cents']==500 and public['flows'][0]['bucket']=='expense'
    assert public['expense_category']=='software_subscriptions'
    with pytest.raises(WorkflowError):record_cash(workflow,{'record_id':row['id'],'amount':'1.00','date':'2011-10-05',
                               'external_reference':'OVER-LIMIT','evidence':'Synthetic', 'source_complete':True},True)
    void_cash(workflow,event['event_id'],'Synthetic wrong allocation',True)
    assert document_flows(archive.catalog(),row)[0]==[]


@pytest.mark.parametrize('changes',[{'payee':'OTHER SYNTHETIC SUPPLIER'},{'original_id':'missing'},
    {'gross':'11.90','net':'10.00','vat':'1.90'}, {'date':'2011-10-02'}, {'vat_rate':7}])
def test_wrong_supplier_reference_date_and_amount_rejected(setup,tmp_path,changes):
    archive,workflow,receipts,source,review=setup
    original=book(receipts,prepare(receipts,review,meta()))['record_id']
    with pytest.raises(WorkflowError):credit(receipts,tmp_path,original,**changes)
    assert len(archive.catalog()['records'])==1


def test_grouped_credit_does_not_mutate_approved_or_source_values(setup,tmp_path):
    archive,workflow,receipts,source,review=setup
    groups=[{'vat_rate':19,'gross':'11.00','net':'9.24','vat':'1.76'}]
    original=book(receipts,prepare(receipts,review,meta(vat_breakdown=groups)))['record_id']
    credit_groups=[{'vat_rate':19,'gross':'5.95','net':'5.00','vat':'.95'}]
    draft=credit(receipts,tmp_path,original,vat_breakdown=credit_groups)
    result=book(receipts,draft);catalog=archive.catalog();row=catalog['records'][result['record_id']]['current']
    assert row['vat_breakdown'][0]['gross']=='-5.95'
    assert row['source_record']['vat_breakdown'][0]['gross']=='5.95'
    assert catalog['local_expense_drafts'][draft['id']]['current']['metadata']['vat_breakdown'][0]['gross']=='5.95'
    assert archive.verify()['ok']
    forged=copy.deepcopy(catalog);forged['records'][row['id']]['current']['gross']='5.95'
    with pytest.raises(ValueError):validate(forged)
    with pytest.raises(WorkflowError):credit(receipts,tmp_path,original,number='SECOND-CREDIT')


def test_credit_with_verified_refund_is_positive_expense_flow(setup,tmp_path):
    archive,workflow,receipts,source,review=setup
    original=book(receipts,prepare(receipts,review,meta()))['record_id']
    draft=credit(receipts,tmp_path,original,pay_date='2011-10-05',paid_amount='5.95',payment_evidence='Synthetic bank refund')
    rid=book(receipts,draft)['record_id'];row=archive.catalog()['records'][rid]['current']
    assert document_flows(archive.catalog(),row)[0][0]['amount_cents']==595


def test_inspect_original_link_prefilled_without_creating_bookkeeping(setup,tmp_path):
    import json
    archive,workflow,receipts,source,review=setup
    original=book(receipts,prepare(receipts,review,meta()))['record_id']
    check=receipts.inspect(pdf(tmp_path/'credit.pdf','Synthetic correction'),tmp_path/'credit-review',original)
    metadata=json.loads(Path(check['metadata']).read_bytes())
    assert metadata['original_id']==original and metadata['document_type']=='supplier_credit'
    assert metadata['gross'] is None and len(archive.catalog()['records'])==1


def test_supplier_credit_xml_type_and_original_reference_bound_to_approval(setup,tmp_path):
    import json
    from test_einvoices import invoice
    from autobookkeeping.einvoices import generate_xml
    from autobookkeeping.receipts import match_structured
    archive,workflow,receipts,source,review=setup
    original=book(receipts,prepare(receipts,review,meta(payee='SYNTHETIC COMPANY',number='TEST-ORIGINAL',
             date='2011-01-01',gross='13.00',net='13.00',vat='0.00',vat_rate=0)))['record_id']
    xml,_=generate_xml(invoice(credit=True)); path=tmp_path/'supplier-credit.xml';path.write_bytes(xml)
    check=receipts.inspect(path,tmp_path/'xml-review')
    data=json.loads(Path(check['metadata']).read_bytes())
    assert data['document_type']=='supplier_credit'
    data.update(category='goods',business_use='business',verification_basis='Synthetic XML credit reviewed',
                original_id=original,correction_reason='Synthetic complete return')
    draft=prepare(receipts,check,data); result=book(receipts,draft)
    row=archive.catalog()['records'][result['record_id']]['current']
    assert row['gross']=='-13.00' and archive.verify()['ok']
    with pytest.raises(WorkflowError):match_structured(dict(data,document_type='expense'),row['structured_invoice'])
