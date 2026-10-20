from types import SimpleNamespace
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
from dataclasses import replace
import pytest
from autobookkeeping.ebay_client import EbayTradingClient
from autobookkeeping.models import EbayOrder, EbayOrderItem
from autobookkeeping.archive import Archive
from autobookkeeping.reconciliation import compare, scan, public_status, matches, findings, explain


def page(number,more,ids):
    return ET.fromstring('<GetOrdersResponse xmlns="urn:ebay:apis:eBLBaseComponents"><HasMoreOrders>'+str(more).lower()+
        '</HasMoreOrders><PaginationResult><PageNumber>'+str(number)+'</PageNumber></PaginationResult><OrderArray>'+''.join(
        '<Order><OrderID>'+i+'</OrderID><OrderStatus>Completed</OrderStatus><Total currencyID="EUR">11</Total></Order>' for i in ids)+'</OrderArray></GetOrdersResponse>')


def client(pages):
    c=EbayTradingClient(SimpleNamespace(ebay_sandbox=True)); requests=[]
    def call(name,body): requests.append(body);return pages.pop(0)
    c._call=call;return c,requests


def test_all_pages_read_with_api_maximum_and_no_silent_truncation():
    c,requests=client([page(1,True,['SYNTHETIC-A']),page(2,False,['SYNTHETIC-B'])])
    assert len(c.get_orders(90,None))==2 and c.orders_complete
    assert '<EntriesPerPage>100</EntriesPerPage>' in requests[0] and '<SortingOrder>Descending</SortingOrder>' in requests[0]
    assert '<PageNumber>2</PageNumber>' in requests[1]
    assert '<CreateTimeFrom>' in requests[0] and '<NumberOfDays>' not in requests[0]
    c,requests=client([page(1,True,['SYNTHETIC-A'])])
    assert len(c.get_orders(30,1))==1 and not c.orders_complete
    with pytest.raises(ValueError):c.get_orders(91,None)
    c,_=client([page(1,True,['SYNTHETIC-A']),page(1,False,['SYNTHETIC-B'])])
    with pytest.raises(RuntimeError):c.get_orders(90,None)


def order():
    return EbayOrder('PAID-SYNTHETIC',sales_record_number='SRN-SYNTHETIC',order_id_aliases=['UNPAID-SYNTHETIC'],
                     total_value=11.0,paid_at=datetime(2011,10,3,tzinfo=timezone.utc),items=[EbayOrderItem('Synthetic title',item_id='ITEM',transaction_id='TRANSACTION')])


def test_srn_and_alias_link_external_reference_without_claiming_local_original():
    o=order();catalog={'records':{}}
    checklist={'items':[{'order_id':'UNPAID-SYNTHETIC','sales_record_number':'SRN-SYNTHETIC','invoice_id':'OLD-ONLY'}]}
    assert compare(catalog,[o],checklist)[0]['state']=='external_reference'
    row={'id':'record','kind':'invoice','source_id':'OLD-ONLY','gross':'11.00','status':'issued','coverage':'complete'}
    catalog['records']['record']={'current':row}
    assert compare(catalog,[o],checklist)[0]['state']=='matched'
    row['gross']='12.00';assert compare(catalog,[o],checklist)[0]['state']=='amount_mismatch'
    assert compare(catalog,[replace(o,paid_at=None)],checklist)[0]['state']=='unpaid'
    assert not matches({'positions':[{'item_id':'I','transaction_id':'T'}]},
                       {'positions':[{'item_id':'I','transaction_id':'T'},{'item_id':'J','transaction_id':'U'}]})


def test_saved_scan_is_encrypted_evidence_not_a_bookkeeping_write(tmp_path):
    repo=tmp_path/'repo';repo.mkdir(); archive=Archive(repo,'synthetic-password');archive.init()
    c=SimpleNamespace(get_orders=lambda **kw:[order()],orders_complete=True,order_window={'from':'2011-10-01T00:00:00+00:00','to':'2011-10-03T12:00:00+00:00'},order_pages=[b'<SyntheticResponse>PRIVATE BUYER</SyntheticResponse>'])
    first=archive.catalog()['records'];result=scan(archive,c,{'items':[]},90,True)
    assert result['counts']=={'missing_invoice':1} and archive.catalog()['records']==first
    assert archive.verify()['ok'] and len(archive.catalog()['documents'])==3
    assert 'PAID-SYNTHETIC' not in str(public_status(archive.catalog()))
    assert all(b'PRIVATE BUYER' not in p.read_bytes() for p in archive.root.rglob('*.enc'))
    c.orders_complete=False
    with pytest.raises(ValueError):scan(archive,c,{},90,True)


def test_explanation_survives_empty_windows_but_not_a_changed_or_returned_case(tmp_path, monkeypatch):
    from autobookkeeping.local_invoices import LocalInvoices
    import autobookkeeping.reconciliation as reconciliation
    archive=Archive(tmp_path/'repo','synthetic-password');archive.repo.mkdir();archive.init()
    client=SimpleNamespace(get_orders=lambda **kw:[order()],orders_complete=True,order_window={},order_pages=[b'<Synthetic/>'])
    moments=iter(f'2011-10-{i:02d}T12:00:00+00:00' for i in range(3,20))
    monkeypatch.setattr(reconciliation,'now',lambda:next(moments))
    scan(archive,client,{'items':[]},90,True)
    case=findings(archive.catalog())[0]; original_scans=archive.catalog()['ebay_reconciliations']
    with pytest.raises(ValueError):explain(LocalInvoices(archive),case['ref'],'PRIVATE REASON',False)
    explain(LocalInvoices(archive),case['ref'],'PRIVATE REASON',True)
    assert archive.catalog()['ebay_reconciliations']==original_scans
    assert findings(archive.catalog())[0]['status']=='explained'
    scan(archive,client,{'items':[]},90,True)
    assert findings(archive.catalog())[0]['status']=='explained'
    client.get_orders=lambda **kw:[];scan(archive,client,{'items':[]},90,True)
    assert public_status(archive.catalog())['explained_findings']==1
    assert 'PRIVATE REASON' not in str(public_status(archive.catalog()))
    client.get_orders=lambda **kw:[replace(order(),total_value=12)]
    scan(archive,client,{'items':[]},90,True)
    assert findings(archive.catalog())[0]['status']=='open'
    with pytest.raises(ValueError):explain(LocalInvoices(archive),case['ref'],'stale',True)
    client.get_orders=lambda **kw:[order()];scan(archive,client,{'items':[]},90,True)
    assert findings(archive.catalog())[0]['status']=='open'
    explain(LocalInvoices(archive),case['ref'],'Second explanation',True)
    explain(LocalInvoices(archive),case['ref'],'Reopen reason',True,True)
    assert findings(archive.catalog())[0]['status']=='open'
    assert len(archive.catalog()['ebay_reconciliation_notes'])==3
    assert archive.verify()['ok']


def test_cancelled_replacement_chain_is_distinct_from_unrelated_duplicate_invoices():
    context={'order_id':'PAID-SYNTHETIC','sales_record_number':'SRN-SYNTHETIC'}
    first=dict(id='original',kind='invoice',source_id='one',gross='11.00',status='cancelled',coverage='complete',**context)
    replacement=dict(first,id='replacement',source_id='two',status='issued',replacement_of='original')
    catalog={'records':{'original':{'current':first},'replacement':{'current':replacement}}}
    assert compare(catalog,[order()],{'items':[]})[0]['state']=='adjusted'
    del replacement['replacement_of']
    assert compare(catalog,[order()],{'items':[]})[0]['state']=='ambiguous'
    replacement['status']='cancelled'
    assert compare(catalog,[order()],{'items':[]})[0]['state']=='ambiguous'
