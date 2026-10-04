import copy
import io
from decimal import Decimal
import pytest
from pypdf import PdfReader
from test_local_invoices import workspace
from autobookkeeping.adjustments import Adjustments, change_tax_profile, fully_cancelled
from autobookkeeping.cashflow import document_flows, record_cash, void_cash
from autobookkeeping.dashboard import projection, html
from autobookkeeping.local_invoices import WorkflowError


def issued(workspace, rates=None):
    archive, workflow, order, checks = workspace
    draft = workflow.prepare(order, checks, rates=rates)
    workflow.activate("0900", "0900", True)
    return workflow.issue(draft["id"], draft["revision"], "0901", order, True)


def finalize(adjust, draft):
    return adjust.issue(draft["id"], draft["revision"], draft["proposed_number"], True)


def test_correction_number_original_immutability_and_stale_draft(workspace):
    archive,workflow,order,checks=workspace; invoice=issued(workspace); adjust=Adjustments(workflow)
    before=copy.deepcopy(archive.catalog()["records"][invoice["id"]]); pdf=archive.read(invoice["documents"][0])
    draft=adjust.prepare(invoice["id"],"correction",{"reason":"Anschrift berichtigt", "changes":{"buyer.street":"Neue Teststraße 2"}})
    stale=adjust.prepare(invoice["id"],"cancellation",{"reason":"Rückgabe"})
    assert draft["proposed_number"]=="0901-K1" and draft["gross"]=="0.00"
    with pytest.raises(WorkflowError):
        adjust.issue(draft["id"],draft["revision"],draft["proposed_number"],False)
    result=finalize(adjust,draft)
    text=PdfReader(io.BytesIO(archive.read(archive.catalog()["records"][result["id"]]["current"]["documents"][0]))).pages[0].extract_text()
    assert "Rechnungsberichtigung 0901-K1" in text and "Neue Teststraße" in text and "Betrag und Steuerbeträge bleiben unverändert" in text
    assert archive.catalog()["records"][invoice["id"]]==before and archive.read(invoice["documents"][0])==pdf
    with pytest.raises(WorkflowError): finalize(adjust,stale)
    cancel=adjust.prepare(invoice["id"],"cancellation",{"reason":"Rückgabe"})
    assert cancel["proposed_number"]=="0902"
    final=finalize(adjust,cancel)
    assert final["refund_executed"] is False and fully_cancelled(archive.catalog(),invoice["id"])
    assert archive.catalog()["records"][final["id"]]["current"]["buyer"]["street"]=="Neue Teststraße 2"
    assert workflow.prepare(order,checks,replacement_of=invoice["id"])["proposed_number"]=="0903"
    with pytest.raises(WorkflowError): adjust.prepare(invoice["id"],"cancellation",{"reason":"Doppelt"})


def test_mixed_tax_partial_refunds_caps_and_rounding(workspace):
    archive,workflow,order,checks=workspace
    change_tax_profile(workflow,False,"Synthetische Regelbesteuerung",True)
    with pytest.raises(ValueError): workflow.prepare(order,checks)
    with pytest.raises(ValueError): workflow.prepare(order,checks,rates=[0,0])
    invoice=issued(workspace,[19,7]); adjust=Adjustments(workflow)
    original=archive.catalog()["records"][invoice["id"]]["current"]
    assert original["vat_breakdown"]==[{"vat_rate":7,"gross":"3.00","net":"2.80","vat":"0.20"}, {"vat_rate":19,"gross":"10.00","net":"8.40","vat":"1.60"}]
    first=adjust.prepare(invoice["id"],"partial_refund",{"reason":"Teilretoure","allocations":[{"position_index":0,"gross":"1.01"}]})
    assert adjust.prepare(invoice["id"],"partial_refund",{"reason":"Teilretoure","allocations":[{"position_index":0,"gross":"1.01"}]})==first
    finalize(adjust,first)
    with pytest.raises(WorkflowError):
        adjust.prepare(invoice["id"],"partial_refund",{"reason":"Zu viel","allocations":[{"position_index":0,"gross":"9.00"}]})
    final=finalize(adjust,adjust.prepare(invoice["id"],"cancellation",{"reason":"Restretoure"}))
    credits=[v["current"] for v in archive.catalog()["records"].values() if v["current"]["kind"]=="credit_note"]
    for key in ("gross","net","vat"):
        assert sum(Decimal(r[key]) for r in credits)==-Decimal(original[key])
    assert fully_cancelled(archive.catalog(),invoice["id"]) and archive.verify()["ok"]


def test_refund_cash_year_and_no_automatic_payment(workspace):
    archive,workflow,order,checks=workspace; invoice=issued(workspace); adjust=Adjustments(workflow)
    credit=finalize(adjust,adjust.prepare(invoice["id"],"partial_refund",{"reason":"Minderung","allocations":[{"position_index":0,"gross":"2.00"}]}))
    row=archive.catalog()["records"][credit["id"]]["current"]
    assert document_flows(archive.catalog(),row)[0]==[]
    payload={"record_id":credit["id"],"amount":"-2.00","date":"2012-01-03","external_reference":"SYNTHETIC PAYMENT KEY","evidence":"Testkonto","source_complete":True}
    with pytest.raises(WorkflowError): record_cash(workflow,payload,False)
    event=record_cash(workflow,payload,True)
    received={"record_id":invoice["id"],"amount":"13.00","date":"2011-10-03","external_reference":"ORIGINAL RECEIPT","evidence":"Testkonto","source_complete":True}
    record_cash(workflow,received,True)
    with pytest.raises(WorkflowError,match="Minderungsbeleg"):
        record_cash(workflow,dict(received,amount="-2.00",external_reference="DOUBLE REFUND"),True)
    assert record_cash(workflow,payload,True)["changed"] is False
    flows,warnings=document_flows(archive.catalog(),row)
    assert flows[0]["amount_cents"]==-200 and flows[0]["date"]=="2012-01-03" and warnings==[]
    with pytest.raises(WorkflowError): record_cash(workflow,dict(payload,external_reference="OVER",amount="-0.01"),True)
    void_cash(workflow,event["event_id"],"Testfehler",True)
    assert document_flows(archive.catalog(),row)[0]==[] and event["event_id"] in archive.catalog()["cash_events"]


def test_cash_override_replaces_source_and_privacy_allowlist(workspace):
    archive,workflow,order,checks=workspace; invoice=issued(workspace)
    payload={"record_id":invoice["id"],"amount":"13.00","date":"2011-10-04","external_reference":"PRIVATE BANK REFERENCE","evidence":"PRIVATE EVIDENCE","source_complete":True}
    record_cash(workflow,payload,True)
    catalog=archive.catalog(); old=catalog["records"]["invoiz:invoice:1"]["current"]
    old.update(id="invoiz:invoice:1",source="invoiz",date="2011-01-01",status="paid")
    snapshot=projection(catalog,"0"*64)
    data=html(snapshot,b'<script type="application/json">__BOOKKEEPING_DATA__</script>')
    assert sum(f["amount_cents"] for r in snapshot["rows"] if r["number"]=="0901" for f in r["flows"])==1300
    for value in (b"SYNTHETIC BUYER",b"Testunternehmer",b"SYNTHETIC DEMO",b"PRIVATE BANK REFERENCE",b"PRIVATE EVIDENCE",b"test-tracking",b"paid-order"):
        assert value not in data
    row=next(r for r in snapshot["rows"] if r["number"]=="0901")
    assert row["flows"][0]["origin"]=="verified"


def test_source_payment_day_stornos_remain_flagged():
    row={"id":"source-1","kind":"invoice","source":"invoiz","status":"cancelled","source_detail":{"payments":[
        {"id":1,"type":"payment","amount":10,"date":"2011-08-22T22:59:00Z","cancellationPaymentId":2},
        {"id":2,"type":"payment","amount":-10,"date":"2012-01-02T11:00:00Z","cancellationPaymentId":1}]}}
    flows,warnings=document_flows({},row)
    assert [f["date"] for f in flows]==["2011-08-23","2012-01-02"] and sum(f["amount_cents"] for f in flows)==0
    assert len(warnings)==2
