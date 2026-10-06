import copy
import json
from pathlib import Path

import pymupdf
import pytest
from lxml import etree as ET

from autobookkeeping.archive import Archive, encoded, sha
from autobookkeeping.einvoices import generate_xml, inspect_xml, validate_xml, xml_tree, CBC, NS
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError
from autobookkeeping.receipts import Receipts
from autobookkeeping.taxes import calculate
from test_local_invoices import workspace

CII_SYNTHETIC = b'''<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100" xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
 <rsm:ExchangedDocumentContext><ram:GuidelineSpecifiedDocumentContextParameter><ram:ID>urn:cen.eu:en16931:2017</ram:ID></ram:GuidelineSpecifiedDocumentContextParameter></rsm:ExchangedDocumentContext>
 <rsm:ExchangedDocument><ram:ID>TEST-CII-1</ram:ID><ram:TypeCode>380</ram:TypeCode><ram:IssueDateTime><udt:DateTimeString format="102">20110101</udt:DateTimeString></ram:IssueDateTime></rsm:ExchangedDocument>
 <rsm:SupplyChainTradeTransaction>
  <ram:IncludedSupplyChainTradeLineItem>
   <ram:AssociatedDocumentLineDocument><ram:LineID>1</ram:LineID></ram:AssociatedDocumentLineDocument>
   <ram:SpecifiedTradeProduct><ram:Name>SYNTHETIC ITEM</ram:Name></ram:SpecifiedTradeProduct>
   <ram:SpecifiedLineTradeAgreement><ram:NetPriceProductTradePrice><ram:ChargeAmount>13.00</ram:ChargeAmount></ram:NetPriceProductTradePrice></ram:SpecifiedLineTradeAgreement>
   <ram:SpecifiedLineTradeDelivery><ram:BilledQuantity unitCode="C62">1</ram:BilledQuantity></ram:SpecifiedLineTradeDelivery>
   <ram:SpecifiedLineTradeSettlement><ram:ApplicableTradeTax><ram:TypeCode>VAT</ram:TypeCode><ram:CategoryCode>E</ram:CategoryCode><ram:RateApplicablePercent>0</ram:RateApplicablePercent></ram:ApplicableTradeTax><ram:SpecifiedTradeSettlementLineMonetarySummation><ram:LineTotalAmount>13.00</ram:LineTotalAmount></ram:SpecifiedTradeSettlementLineMonetarySummation></ram:SpecifiedLineTradeSettlement>
  </ram:IncludedSupplyChainTradeLineItem>
  <ram:ApplicableHeaderTradeAgreement>
   <ram:SellerTradeParty><ram:ID>TEST-ONLY</ram:ID><ram:Name>SYNTHETIC COMPANY</ram:Name><ram:PostalTradeAddress><ram:PostcodeCode>00000</ram:PostcodeCode><ram:LineOne>TEST 1</ram:LineOne><ram:CityName>TEST</ram:CityName><ram:CountryID>DE</ram:CountryID></ram:PostalTradeAddress><ram:SpecifiedTaxRegistration><ram:ID schemeID="FC">TEST-ONLY</ram:ID></ram:SpecifiedTaxRegistration></ram:SellerTradeParty>
   <ram:BuyerTradeParty><ram:Name>SYNTHETIC BUYER</ram:Name><ram:PostalTradeAddress><ram:PostcodeCode>00000</ram:PostcodeCode><ram:LineOne>TEST 2</ram:LineOne><ram:CityName>TEST</ram:CityName><ram:CountryID>DE</ram:CountryID></ram:PostalTradeAddress></ram:BuyerTradeParty>
  </ram:ApplicableHeaderTradeAgreement>
  <ram:ApplicableHeaderTradeDelivery/>
  <ram:ApplicableHeaderTradeSettlement><ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode><ram:ApplicableTradeTax><ram:CalculatedAmount>0.00</ram:CalculatedAmount><ram:TypeCode>VAT</ram:TypeCode><ram:ExemptionReason>Paragraph 19 UStG</ram:ExemptionReason><ram:BasisAmount>13.00</ram:BasisAmount><ram:CategoryCode>E</ram:CategoryCode><ram:RateApplicablePercent>0</ram:RateApplicablePercent></ram:ApplicableTradeTax><ram:SpecifiedTradeSettlementHeaderMonetarySummation><ram:LineTotalAmount>13.00</ram:LineTotalAmount><ram:TaxBasisTotalAmount>13.00</ram:TaxBasisTotalAmount><ram:TaxTotalAmount currencyID="EUR">0.00</ram:TaxTotalAmount><ram:GrandTotalAmount>13.00</ram:GrandTotalAmount><ram:TotalPrepaidAmount>13.00</ram:TotalPrepaidAmount><ram:DuePayableAmount>0.00</ram:DuePayableAmount></ram:SpecifiedTradeSettlementHeaderMonetarySummation></ram:ApplicableHeaderTradeSettlement>
 </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>'''


def test_cii_validated_and_total_not_confused_with_zero_outstanding():
    result=inspect_xml(CII_SYNTHETIC)
    assert result['validation']['en16931_valid'],result['validation']
    assert result['metadata']['gross']=='13.00' and result['metadata']['pay_date'] is None
    assert result['metadata']['date']=='2011-01-01'


def invoice(small=True, credit=False):
    party={'name':'SYNTHETIC COMPANY','street':'TEST 1','city':'TEST','postal_code':'00000',
           'country_iso':'DE','tax_number':'TEST-ONLY','tax_note':'Steuerbefreit nach Paragraph 19 UStG'}
    positions=[{'title':'SYNTHETIC ITEM','quantity':3,'gross':'13.00'}]
    if not small:positions.append({'title':'SYNTHETIC SECOND ITEM','quantity':1,'gross':'1.07'})
    totals=calculate(positions,small,None if small else [19,7])
    result=dict(id='test:1',number='TEST-1',date='2011-01-01',seller=party,buyer=copy.deepcopy(party),
                positions=positions,**totals)
    if credit:
        result.update(kind='credit_note',original_number='TEST-ORIGINAL',original_date='2011-01-01')
        for row in [result,*result['positions'],*result['vat_breakdown']]:
            for field in ('gross','net','vat'):row[field]=str(-__import__('decimal').Decimal(row[field]))
    return result


@pytest.mark.parametrize('small,credit',[(True,False),(False,False),(True,True),(False,True)])
def test_generated_xml_valid_totals_and_credit_reference(small,credit):
    row=invoice(small,credit);data,validation=generate_xml(row)
    assert validation['xsd_valid'] and validation['en16931_valid'] and not validation['cius_validated']
    result=inspect_xml(data)
    assert result['metadata']['gross']==row['gross'].lstrip('-')
    assert result['metadata']['pay_date'] is None
    assert result['document_type']==('credit_note' if credit else 'invoice')
    assert result['metadata']['category'] is None and result['metadata']['business_use'] is None
    assert b'EndpointID' not in data
    if credit:assert b'TEST-ORIGINAL' in data
    else:assert xml_tree(data).find('cac:LegalMonetaryTotal/cbc:PayableAmount',NS).text=='0.00'


def test_draft_number_and_invalid_xml_fail_closed():
    row=invoice();row['number']=None
    data,_=generate_xml(row,draft=True)
    assert b'TESTENTWURF' in data and b'TEST-1' in data
    with pytest.raises(ValueError):generate_xml(row)
    root=xml_tree(data);root.find('cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount',NS).text='999.00'
    invalid=ET.tostring(root)
    assert not validate_xml(invalid)['en16931_valid'] and inspect_xml(invalid)['metadata'] is None
    minimal=b'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"/>'
    assert inspect_xml(minimal)['metadata'] is None
    with pytest.raises(ValueError):xml_tree(b'<!DOCTYPE x [<!ENTITY private SYSTEM "file:///missing">]><x>&private;</x>')
    with pytest.raises(ValueError):xml_tree(b'<broken>')


def complete(path):
    data=json.loads(path.read_bytes())
    data.update(category='goods',business_use='business',verification_basis='Synthetic XML and original checked')
    path.write_bytes(encoded(data));return data


@pytest.mark.parametrize('hybrid',[False,True])
def test_structured_import_original_bytes_approval_and_metadata_binding(tmp_path,hybrid):
    repo=tmp_path/'repo';repo.mkdir();archive=Archive(repo,'synthetic-password');archive.init()
    receipts=Receipts(LocalInvoices(archive));xml,_=generate_xml(invoice())
    if hybrid:
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((30,30),'SYNTHETIC DISPLAY')
            pdf.embfile_add('factur-x.xml',xml)
            original=pdf.tobytes()
        source=tmp_path/'source.pdf'
    else:source=tmp_path/'source.xml';original=xml
    source.write_bytes(original)
    review=receipts.inspect(source,tmp_path/'review')
    assert review['xml_validation']['en16931_valid'] and review['structured_invoice']
    metadata=Path(review['metadata']);fields=complete(metadata)
    assert fields['gross']=='13.00' and fields['pay_date'] is None
    fields['gross']='14.00';fields['net']='14.00';fields['vat_breakdown'][0].update(gross='14.00',net='14.00')
    metadata.write_bytes(encoded(fields))
    with pytest.raises(WorkflowError):receipts.prepare(Path(review['review']),metadata)
    receipts.inspect(source,tmp_path/'review-again')
    metadata.write_bytes((tmp_path/'review-again/metadaten.json').read_bytes());complete(metadata)
    draft=receipts.prepare(Path(review['review']),metadata)
    assert not archive.catalog()['records']
    with pytest.raises(WorkflowError):receipts.book(draft['id'],draft['revision'],False)
    booked=receipts.book(draft['id'],draft['revision'],True)
    row=archive.catalog()['records'][booked['record_id']]['current']
    assert archive.read(row['documents'][0])==original and source.read_bytes()==original
    assert row['structured_invoice']['validation']['en16931_valid']
    assert any(archive.read(n)==xml for n in row['documents'])
    assert not any(b'SYNTHETIC COMPANY' in p.read_bytes() for p in archive.root.rglob('*') if p.is_file())
    assert archive.verify()['ok']
    assert receipts.book(draft['id'],draft['revision'],True)['changed'] is False


def test_multiple_embedded_invoices_and_incoming_credit_rejected(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();archive=Archive(repo,'synthetic-password');archive.init();receipts=Receipts(LocalInvoices(archive))
    xml,_=generate_xml(invoice());source=tmp_path/'multiple.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page();pdf.embfile_add('one.xml',xml);pdf.embfile_add('two.xml',xml);source.write_bytes(pdf.tobytes())
    with pytest.raises(WorkflowError):receipts.inspect(source,tmp_path/'multiple-review')
    xml,_=generate_xml(invoice(credit=True));source=tmp_path/'credit.xml';source.write_bytes(xml)
    review=receipts.inspect(source,tmp_path/'credit-review');metadata=Path(review['metadata']);complete(metadata)
    with pytest.raises(WorkflowError):receipts.prepare(Path(review['review']),metadata)


def test_issue_binds_xml_validation_and_draft_preview_no_number(workspace,tmp_path):
    archive,workflow,order,checks=workspace
    draft=workflow.prepare(order,checks)
    workflow.preview(draft['id'],tmp_path/'preview-xml',True)
    assert (tmp_path/'preview-xml/rechnung.xml').is_file()
    assert archive.catalog()['local_invoice_drafts'][draft['id']]['current']['number'] is None
    workflow.activate('0900','0900',True)
    result=workflow.issue(draft['id'],draft['revision'],'0901',order,True)
    row=archive.catalog()['records'][result['id']]['current']
    assert len(row['documents'])==3 and row['e_invoice']['en16931_valid']
    xml=next(archive.read(n) for n in row['documents'] if n.endswith('.xml.enc'))
    assert inspect_xml(xml)['metadata']['number']=='0901'
    workflow.preview(result['id'],tmp_path/'issued-xml',True)
    assert (tmp_path/'issued-xml/rechnung.xml').read_bytes()==xml
