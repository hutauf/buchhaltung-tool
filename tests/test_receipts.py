import copy
import io
import json
from pathlib import Path
import pytest
from reportlab.pdfgen import canvas
import pymupdf

from autobookkeeping.archive import Archive, encoded, sha
from autobookkeeping.cashflow import document_flows
from autobookkeeping.dashboard import html, projection
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError
from autobookkeeping.receipts import Receipts, validate_metadata


def pdf(path,text="PRIVATE TEST SUPPLIER · Invoice ONLY-TEST-1 · 11.00 EUR"):
    buffer=io.BytesIO();c=canvas.Canvas(buffer);c.drawString(30,800,text);c.save();path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(buffer.getvalue());return path


def meta(**overrides):
    result={"payee":"PRIVATE TEST SUPPLIER","number":"ONLY-TEST-1","date":"2011-10-03","currency":"EUR",
            "gross":"11.00","net":"9.24","vat":"1.76","vat_rate":19,"tax_treatment":"as_documented",
            "tax_review_required":False,"description":"SYNTHETIC SOFTWARE DESCRIPTION","category":"software_subscriptions",
            "supplier_country":"DE","business_use":"business","pay_date":None,"verification_basis":"Synthetic original page 1"}
    result.update(overrides);return result


@pytest.fixture
def setup(tmp_path):
    repo=tmp_path/"repo";repo.mkdir();archive=Archive(repo,"synthetic-password");archive.init()
    workflow=LocalInvoices(archive);receipts=Receipts(workflow);source=pdf(tmp_path/"Downloads/test.pdf")
    review=receipts.inspect(source,tmp_path/"review")
    return archive,workflow,receipts,source,review


def prepare(receipts,review,metadata):
    path=Path(review["metadata"]);path.write_bytes(encoded(metadata));return receipts.prepare(Path(review["review"]),path)


def book(receipts,draft):return receipts.book(draft["id"],draft["revision"],True)


def test_unpaid_generic_receipt_approval_encryption_privacy_and_idempotence(setup,tmp_path):
    archive,workflow,receipts,source,review=setup;original=source.read_bytes()
    assert source.is_file() and review["pages"]==1 and Path(review["images"][0]).is_file()
    draft=prepare(receipts,review,meta())
    assert len(archive.catalog()["records"])==0 and draft["booked"] is False
    assert prepare(receipts,review,meta())==draft
    snapshot=projection(archive.catalog(),"0"*64)
    assert snapshot["rows"][0]["kind"]=="draft" and snapshot["rows"][0]["flows"]==[]
    for p in archive.root.rglob("*"):
        if p.is_file():assert b"PRIVATE TEST SUPPLIER" not in p.read_bytes()
    with pytest.raises(WorkflowError):receipts.book(draft["id"],draft["revision"],False)
    with pytest.raises(WorkflowError):receipts.book(draft["id"],"wrong-revision",True)
    result=book(receipts,draft);row=archive.catalog()["records"][result["record_id"]]["current"]
    assert row["gross"]=="11.00" and row["vat"]=="1.76" and source.read_bytes()==original
    assert archive.read(row["documents"][0])==original and archive.verify()["ok"]
    assert document_flows(archive.catalog(),row)[0]==[]
    assert projection(archive.catalog(),"0"*64)["rows"][0]["expense_category"]=="software_subscriptions"
    assert book(receipts,draft)["changed"] is False
    html_bytes=html(projection(archive.catalog(),"0"*64),b'__BOOKKEEPING_DATA__')
    assert b"PRIVATE" not in html_bytes and b"SYNTHETIC SOFTWARE DESCRIPTION" not in html_bytes
    again=receipts.inspect(source,tmp_path/"already-booked")
    assert again["existing_records"]==[result["record_id"]]


def test_payment_partial_and_metadata_revision_bound_to_approval(setup):
    archive,workflow,receipts,source,review=setup
    first=prepare(receipts,review,meta())
    second=prepare(receipts,review,meta(pay_date="2011-10-04",paid_amount="5.00",payment_evidence="Verified partial payment"))
    assert first["revision"]!=second["revision"]
    with pytest.raises(WorkflowError):book(receipts,first)
    result=book(receipts,second);row=archive.catalog()["records"][result["record_id"]]["current"]
    flows,warnings=document_flows(archive.catalog(),row)
    assert flows[0]["amount_cents"]==-500 and flows[0]["date"]=="2011-10-04" and warnings==["Ausgabe erst teilweise bezahlt"]


def test_identical_supplier_invoice_number_blocks_redownload_with_other_hash(setup,tmp_path):
    archive,workflow,receipts,source,review=setup;first=book(receipts,prepare(receipts,review,meta()))
    other=pdf(tmp_path/"another.pdf","Different binary, same supplier invoice number")
    second_review=receipts.inspect(other,tmp_path/"another-review")
    assert second_review["existing_records"]==[]
    with pytest.raises(WorkflowError,match="bereits archiviert"):
        prepare(receipts,second_review,meta(payee=" private test supplier "))
    assert len(archive.catalog()["records"])==1


def test_possible_duplicate_requires_concrete_explanation_and_rechecks_new_records(setup,tmp_path):
    archive,workflow,receipts,source,review=setup;book(receipts,prepare(receipts,review,meta()))
    other=pdf(tmp_path/"another.pdf","Other expense, same supplier date and amount")
    next_review=receipts.inspect(other,tmp_path/"next-review")
    proposed=prepare(receipts,next_review,meta(number=None))
    assert proposed["requires_duplicate_review"] and len(archive.catalog()["records"])==1
    allowed=prepare(receipts,next_review,meta(number=None,duplicate_review="Separate receipt; both originals checked"))
    assert book(receipts,allowed)["changed"] and len(archive.catalog()["records"])==2


def test_correct_encrypted_path_reused_without_new_original(setup,tmp_path):
    archive,workflow,receipts,source,review=setup;first=prepare(receipts,review,meta())
    name=first["documents"][0];cipher=(archive.root/name).read_bytes()
    new_review=receipts.inspect(archive.root/name,tmp_path/"encrypted-review")
    second=prepare(receipts,new_review,meta(description="Corrected expense description"))
    assert second["documents"]==[name] and (archive.root/name).read_bytes()==cipher
    assert len(archive.catalog()["documents"])==1


def test_plain_original_dropped_inside_bookkeeping_safely_relocated(setup,tmp_path):
    archive,workflow,receipts,source,review=setup
    incoming=pdf(archive.root/"2011/Ausgaben/drop.pdf");original=incoming.read_bytes()
    result=receipts.inspect(incoming,tmp_path/"inside-review")
    assert result["source_relocated_outside"] and not incoming.exists()
    assert (tmp_path/"inside-review/eingereicht.pdf").read_bytes()==original and archive.verify()["ok"]
    draft=prepare(receipts,result,meta());assert archive.read(draft["documents"][0])==original


def test_image_receipt_and_unbooked_dhl_guard(setup,tmp_path):
    archive,workflow,receipts,source,review=setup
    doc=pymupdf.open();page=doc.new_page(width=300,height=300);page.insert_text((10,30),"SYNTHETIC IMAGE RECEIPT")
    png=page.get_pixmap().tobytes("png");image=tmp_path/"image.png";image.write_bytes(png)
    result=receipts.inspect(image,tmp_path/"image-review");draft=prepare(receipts,result,meta(number="IMAGE-ONLY"))
    assert draft["documents"][0].endswith(".png.enc") and archive.read(draft["documents"][0])==png
    catalog=archive.catalog();catalog["documents"][draft["documents"][0]]["role"]="unbooked_receipt";archive.save_catalog(catalog)
    with pytest.raises(WorkflowError,match="DHL"):
        prepare(receipts,result,meta(number="IMAGE-ONLY"))
    with pytest.raises(WorkflowError,match="DHL"):
        book(receipts,draft)


def test_recover_interrupted_booking_and_original_revision_tampering(setup,monkeypatch):
    archive,workflow,receipts,source,review=setup;draft=prepare(receipts,review,meta())
    original_save=archive.save_catalog
    def power_loss(catalog):raise OSError("synthetic interruption")
    monkeypatch.setattr(archive,"save_catalog",power_loss)
    with pytest.raises(OSError):book(receipts,draft)
    assert workflow.journal.exists() and b"PRIVATE TEST SUPPLIER" not in workflow.journal.read_bytes()
    monkeypatch.setattr(archive,"save_catalog",original_save)
    assert workflow.recover() and book(receipts,draft)["changed"] is False
    assert len(archive.catalog()["records"])==1


@pytest.mark.parametrize("changes",[
    {"gross":"11.01"},{"gross":"11.001"},{"pay_date":"2011-10-04"},{"vat_rate":0,"tax_treatment":"no_vat_shown"},
    {"supplier_country":"IE"},{"currency":"USD"},{"date":"2011-02-31"},{"business_use":None},{"id":"custom"}])
def test_metadata_guards(changes):
    with pytest.raises((ValueError,WorkflowError)):validate_metadata(meta(**changes))


def test_foreign_no_tax_shown_is_marked_and_unknown_not_assumed_zero(setup):
    archive,workflow,receipts,source,review=setup
    draft=prepare(receipts,review,meta(net="11.00",vat="0.00",vat_rate=None,tax_treatment="no_vat_shown",
         supplier_country="IE",tax_review_required=True,tax_review_note="Foreign invoice: separately check tax handling"))
    result=book(receipts,draft);row=archive.catalog()["records"][result["record_id"]]["current"]
    public=projection(archive.catalog(),"0"*64)["rows"][0]
    assert row["vat_rate"] is None and public["vat_rates"]==[] and len(public["warnings"])==2


def test_mixed_tax_groups_preserved_and_displayed(setup):
    archive,workflow,receipts,source,review=setup
    draft=prepare(receipts,review,meta(gross="226.00",net="200.00",vat="26.00",vat_rate=None,tax_treatment="mixed",vat_breakdown=[
         {"vat_rate":19,"gross":"119.00","net":"100.00","vat":"19.00"},
         {"vat_rate":7,"gross":"107.00","net":"100.00","vat":"7.00"}]))
    assert projection(archive.catalog(),"0"*64)["rows"][0]["vat_rates"]==[7,19]
    book(receipts,draft)
    assert projection(archive.catalog(),"0"*64)["rows"][0]["vat_rates"]==[7,19]


def test_tax_groups_must_not_silently_round_receipt_values():
    with pytest.raises(WorkflowError,match="Centbeträge"):
        validate_metadata(meta(tax_treatment="mixed",vat_rate=None,vat_breakdown=[
            {"gross":"11.001","net":"9.241","vat":"1.760","vat_rate":19}]))
