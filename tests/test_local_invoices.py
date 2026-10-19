import copy
import io
from datetime import datetime, timezone

import pytest
from pypdf import PdfReader

from autobookkeeping.archive import Archive, atomic, encoded
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError, same_order
from autobookkeeping.models import Address, EbayOrder, EbayOrderItem


@pytest.fixture
def workspace(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    (repo / "bookkeeping_checklist.json").write_bytes(encoded({"items": []}))
    archive = Archive(repo, "synthetic-test-password"); archive.init()
    catalog = archive.catalog()
    catalog["records"]["imported:invoice:1"] = {"current": {"kind": "invoice", "number": "0900",
        "gross": "5.00", "net": "5.00", "vat": "0.00", "vat_rate": 0, "year": "2011", "coverage": "complete",
        "source_record": {"customerData": {"number": "old-order"}}, "documents": []}, "history": []}
    archive.save_catalog(catalog)
    workflow = LocalInvoices(archive)
    workflow.configure({"name": "Testunternehmer", "street": "Testweg 3", "postal_code": "12345", "city": "Teststadt",
        "country_iso": "DE", "tax_number": "TEST-ONLY", "small_business": True,
        "tax_note": "Gemäß § 19 Abs. 1 UStG wird keine Umsatzsteuer berechnet.", "introduction": "Vielen Dank für Ihren Kauf."}, "0900", {"synthetic": True})
    order = EbayOrder(order_id="paid-order", sales_record_number="9998", order_status="Completed",
        paid_at=datetime(2011,1,10,12,0,tzinfo=timezone.utc), shipped_at=datetime(2011,1,10,13,0,tzinfo=timezone.utc),
        total_value=13.00, shipping_cost=3.00, currency="EUR", tracking_number="test-tracking",
        shipping_address=Address(name="SYNTHETIC BUYER",street1="Teststraße 1",postal_code="12345",city="Teststadt",country_iso="DE"),
        items=[EbayOrderItem(title="SYNTHETIC DEMO ITEM", price=10.00, item_id="item-1", transaction_id="transaction-1")])
    checks = {"vine_checked": True, "dhl_checked": True, "invoice_matches": [], "expense_matches": []}
    return archive, workflow, order, checks


def test_draft_pdf_totals_privacy_idempotence_and_outside(workspace, tmp_path):
    archive, workflow, order, checks = workspace
    draft = workflow.prepare(order, checks)
    assert draft["number"] is None and draft["proposed_number"] == "0901" and not draft["number_reserved"]
    assert len(archive.catalog()["records"]) == 1
    assert workflow.prepare(order, checks) == draft
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(archive.read(draft["documents"][0]))).pages)
    assert "TESTENTWURF" in text and "noch nicht vergeben" in text and "0901" not in text
    assert "10,00 €" in text and "3,00 €" in text and "13,00 €" in text and "§ 19" in text
    assert "SYNTHETIC BUYER" in text and "Teststraße" in text
    assert not any(b"SYNTHETIC BUYER" in p.read_bytes() for p in archive.root.rglob("*") if p.is_file())
    with pytest.raises(ValueError):
        workflow.preview(draft["id"], archive.repo / "preview")
    result = workflow.preview(draft["id"], tmp_path / "preview")
    assert result["number"] is None
    assert (tmp_path / "preview/rechnung.pdf").is_file()
    with pytest.raises(ValueError):
        workflow.preview(draft["id"], tmp_path / "preview")


def test_read_checks_unpaid_sum_and_tax_scope(workspace):
    archive, workflow, order, checks = workspace
    with pytest.raises(WorkflowError):
        workflow.prepare(order, dict(checks, invoice_matches=[{"id": 42}]))
    with pytest.raises(WorkflowError):
        workflow.prepare(order, dict(checks, dhl_checked=False))
    unpaid = copy.deepcopy(order); unpaid.paid_at = None
    with pytest.raises(WorkflowError):
        workflow.prepare(unpaid, checks)
    bad = copy.deepcopy(order); bad.total_value = 13.01
    with pytest.raises(WorkflowError):
        workflow.prepare(bad, checks)
    foreign = copy.deepcopy(order); foreign.shipping_address.country_iso = "AT"
    with pytest.raises(WorkflowError):
        workflow.prepare(foreign, checks)
    assert not archive.catalog()["local_invoice_drafts"]


def test_srn_alias_and_transaction_identity(workspace):
    archive, workflow, order, checks = workspace
    first = workflow.prepare(order, checks)
    order.order_id = "different-paid-id"; order.order_id_aliases = ["paid-order"]
    second = workflow.prepare(order, checks)
    assert second["id"] == first["id"] and second["revision"] != first["revision"]
    assert len(archive.catalog()["local_invoice_drafts"]) == 1
    assert same_order({"order_id":"unpaid", "sales_record_number":"9998"}, {"order_id":"paid", "sales_record_number":"9998"})
    assert same_order({"positions":[{"item_id":"i","transaction_id":"t"}]}, {"positions":[{"item_id":"i","transaction_id":"t"}]})
    assert not same_order({"order_id":"a","positions":[{"title":"Same title"}]}, {"order_id":"b","positions":[{"title":"Same title"}]})


def test_live_checklist_and_imported_archive_duplicates(workspace):
    archive, workflow, order, checks = workspace
    atomic(archive.repo / "bookkeeping_checklist.json", encoded({"items":[{"order_id":"old-id", "sales_record_number":"9998","invoice_id":9}]}))
    with pytest.raises(WorkflowError):
        workflow.prepare(order, checks)
    atomic(archive.repo / "bookkeeping_checklist.json", encoded({"items":[]}))
    order.order_id = "old-order"
    with pytest.raises(WorkflowError):
        workflow.prepare(order, checks)


def test_discard_does_not_consume_number(workspace):
    archive, workflow, order, checks = workspace
    first = workflow.prepare(order, checks)
    assert workflow.discard(first["id"])["number_consumed"] is False
    second = workflow.prepare(order, checks)
    assert first["id"] != second["id"] and second["proposed_number"] == "0901"


def test_manual_invoice_without_services_has_no_invented_payment(workspace):
    from autobookkeeping.cashflow import document_flows
    archive,workflow,_,_=workspace
    payload={'reference':'SYNTHETIC-MANUAL-1','verification_basis':'Synthetic signed order',
             'buyer':{'name':'SYNTHETIC BUYER','street':'Testweg 4','postal_code':'12345','city':'Teststadt','country':'Deutschland','country_iso':'DE'},
             'delivery_date':'2011-01-10','positions':[{'title':'SYNTHETIC ITEM','quantity':2,'unit_gross':'7.50'}]}
    draft=workflow.prepare_manual(payload)
    assert workflow.prepare_manual(payload)==draft
    assert draft['gross']=='15.00' and draft['number'] is None
    workflow.activate('0900','0900',True)
    issued=workflow.issue(draft['id'],draft['revision'],'0901',None,True)
    record=archive.catalog()['records'][issued['id']]['current']
    assert record['entry_source']=='manual' and record['payment_status']=='unpaid' and record['outstanding']=='15.00'
    assert record['pay_date'] is None and document_flows(archive.catalog(),record)[0]==[]
    text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(archive.read(issued['documents'][0]))).pages)
    assert 'Auftragsreferenz' in text and 'SYNTHETIC-MANUAL-1' in text and 'Bereits über eBay bezahlt' not in text
    assert any(n.endswith('.xml.enc') for n in issued['documents'])
    from lxml import etree as ET
    xml=ET.fromstring(archive.read(next(n for n in issued['documents'] if n.endswith('.xml.enc'))))
    assert xml.xpath("string(//*[local-name()='PrepaidAmount'])")=='0.00'
    assert xml.xpath("string(//*[local-name()='PayableAmount'])")=='15.00'
    assert archive.verify()['ok']
    with pytest.raises(WorkflowError,match='bereits'):
        workflow.prepare_manual(payload)
    from autobookkeeping.adjustments import Adjustments
    adjustments=Adjustments(workflow)
    cancel=adjustments.prepare(issued['id'],'cancellation',{'reason':'Synthetic correction test'})
    adjustments.issue(cancel['id'],cancel['revision'],'0902',True)
    replacement=workflow.prepare_manual(payload,replacement_of=issued['id'])
    assert replacement['proposed_number']=='0903'
    corrected=workflow.issue(replacement['id'],replacement['revision'],'0903',None,True)
    assert archive.catalog()['records'][corrected['id']]['current']['replacement_of']==issued['id']
    assert document_flows(archive.catalog(),archive.catalog()['records'][corrected['id']]['current'])[0]==[]


def test_unconfigured_vine_is_optional_but_failed_checks_are_not_ignored(workspace):
    _,workflow,order,checks=workspace
    draft=workflow.prepare(order,dict(checks,vine_checked=False,vine_status='not_configured'))
    assert draft['number'] is None
    with pytest.raises(WorkflowError): workflow.prepare(order,dict(checks,vine_checked=False,vine_status='failed'))
    import runpy
    from pathlib import Path
    from types import SimpleNamespace
    module=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/local_invoice.py'))
    order.tracking_number=None
    result=module['read_checks'](order,SimpleNamespace(vine_backend_url='',vine_backend_token=''))
    assert result['vine_status']=='not_configured' and result['vine_checked'] is False
    with pytest.raises(WorkflowError,match='unvollständig'):
        module['read_checks'](order,SimpleNamespace(vine_backend_url='https://example.invalid',vine_backend_token=''))


def test_manual_cli_uses_no_external_client_for_prepare_or_issue(workspace,monkeypatch):
    import runpy
    import sys
    from pathlib import Path
    from autobookkeeping import guided
    archive,workflow,_,_=workspace
    payload={'reference':'SYNTHETIC-CLI-MANUAL','verification_basis':'Synthetic local sale reviewed',
             'buyer':{'name':'SYNTHETIC BUYER','street':'Testweg 4','postal_code':'12345','city':'Teststadt','country':'Deutschland','country_iso':'DE'},
             'delivery_date':'2011-01-10','positions':[{'title':'SYNTHETIC ITEM','quantity':1,'unit_gross':'3.50'}]}
    module=runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/local_invoice.py'))
    class OfflinePublication:
        enabled=False
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
    g=module['main'].__globals__
    g.update(data_root=lambda:archive.repo,Publication=OfflinePublication,Archive=lambda _:archive)
    def forbidden():raise AssertionError('Manual flow must not load service settings')
    g['load_settings']=forbidden
    monkeypatch.setattr(guided,'manual_invoice',lambda:payload)
    monkeypatch.setattr(sys,'argv',['local_invoice.py','manual-prepare','--interactive'])
    draft=module['main']()
    workflow.activate('0900','0900',True)
    monkeypatch.setattr(sys,'argv',['local_invoice.py','issue',draft['id'],'--revision',draft['revision'],'--number','0901','--approved'])
    issued=module['main']()
    assert issued['number']=='0901' and archive.verify()['ok']


def test_finalize_guard_and_immutable_numbered_original(workspace, tmp_path):
    archive, workflow, order, checks = workspace
    draft = workflow.prepare(order, checks)
    with pytest.raises(WorkflowError):
        workflow.issue(draft["id"],draft["revision"],"0901",order,False)
    with pytest.raises(WorkflowError):
        workflow.issue(draft["id"],draft["revision"],"0901",order,True)
    with pytest.raises(WorkflowError):
        workflow.activate("0900","0900",False)
    with pytest.raises(WorkflowError):
        workflow.activate("0900","0901",True)
    workflow.activate("0900","0900",True)
    with pytest.raises(WorkflowError):
        workflow.issue(draft["id"],"old-revision","0901",order,True)
    with pytest.raises(WorkflowError):
        workflow.issue(draft["id"],draft["revision"],"0902",order,True)
    changed = copy.deepcopy(order); changed.shipping_address.street1 = "Andere Straße"
    with pytest.raises(WorkflowError):
        workflow.issue(draft["id"],draft["revision"],"0901",changed,True)
    issued = workflow.issue(draft["id"],draft["revision"],"0901",order,True)
    assert issued["number"] == "0901" and issued["number_reserved"]
    original = archive.read(issued["documents"][0])
    text = PdfReader(io.BytesIO(original)).pages[0].extract_text()
    assert "Rechnung 0901" in text and "TESTENTWURF" not in text
    final_preview = workflow.preview(draft["id"], tmp_path / "issued-preview")
    assert final_preview["id"] == issued["id"]
    assert (tmp_path / "issued-preview/rechnung.pdf").read_bytes() == original
    with pytest.raises(WorkflowError):
        workflow.issue(draft["id"],draft["revision"],"0902",order,True)
    with pytest.raises(WorkflowError):
        workflow.discard(draft["id"])
    with pytest.raises(WorkflowError):
        workflow.prepare(order, checks)
    assert archive.read(issued["documents"][0]) == original
    order.order_id="second-order"; order.sales_record_number="9999"; order.items[0].transaction_id="transaction-2"
    assert workflow.prepare(order,checks)["proposed_number"] == "0902"


def test_receipt_candidate_not_booked_until_invoice_and_approval(workspace):
    archive, workflow, order, checks = workspace
    # Synthetic original PDF; metadata amounts deliberately differ from shipping charged.
    data = b"%PDF-1.4 SYNTHETIC RECEIPT"
    receipt = {"order_id":order.order_id,"gross":"5.00","date":"2011-10-03","vat_rate":0,
        "payee":"DHL","product":"Paket","cart_id":"synthetic-cart","number":"synthetic-receipt",
        "verified":True,"verification_basis":"synthetic test"}
    draft = workflow.prepare(order,checks,(receipt,data))
    assert len(archive.catalog()["records"]) == 1
    assert workflow.prepare(order,checks,(receipt,data)) == draft
    receipt["gross"]="5.10"
    changed = workflow.prepare(order,checks,(receipt,data))
    assert changed["revision"] != draft["revision"]
    workflow.activate("0900","0900",True)
    issued = workflow.issue(changed["id"],changed["revision"],"0901",order,True)
    with pytest.raises(WorkflowError):
        workflow.expense(issued["id"],changed["receipt_candidate_sha256"],False)
    with pytest.raises(WorkflowError):
        workflow.expense(issued["id"],"wrong-receipt",True)
    expense = workflow.expense(issued["id"],changed["receipt_candidate_sha256"],True)
    assert expense["gross"] == "5.10" and expense["invoice_number"] == "0901"
    assert archive.catalog()["local_workflow"][issued["id"]]["status"] == "ok"
    with pytest.raises(WorkflowError):
        workflow.expense(issued["id"],changed["receipt_candidate_sha256"],True)


def test_recovery_of_interrupted_number_assignment(workspace, monkeypatch):
    archive, workflow, order, checks = workspace
    draft = workflow.prepare(order,checks); workflow.activate("0900","0900",True)
    original_save = archive.save_catalog
    def power_loss(catalog):
        raise OSError("synthetic power loss between PDF and database")
    monkeypatch.setattr(archive,"save_catalog",power_loss)
    with pytest.raises(OSError):
        workflow.issue(draft["id"],draft["revision"],"0901",order,True)
    assert workflow.journal.exists()
    assert b"SYNTHETIC BUYER" not in workflow.journal.read_bytes()
    monkeypatch.setattr(archive,"save_catalog",original_save)
    assert workflow.recover()
    assert not workflow.journal.exists() and archive.verify()["ok"]
    with pytest.raises(WorkflowError):
        workflow.issue(draft["id"],draft["revision"],"0901",order,True)
    assert sum(v["current"].get("number")=="0901" for v in archive.catalog()["records"].values()) == 1


def test_multipage_unicode_and_visible_draft_on_every_page(workspace):
    archive,workflow,order,checks=workspace
    order.items = [EbayOrderItem(title="Übergrößen · Testartikel "+str(i),price=1,item_id=str(i),transaction_id=str(i)) for i in range(70)]
    order.shipping_cost=0; order.total_value=70
    draft=workflow.prepare(order,checks)
    pages=PdfReader(io.BytesIO(archive.read(draft["documents"][0]))).pages
    assert len(pages) >= 3
    assert all("TESTENTWURF" in page.extract_text() and "Steuernummer" in page.extract_text() for page in pages)
    assert "Übergrößen" in pages[0].extract_text()
