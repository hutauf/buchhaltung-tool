import copy
import json
import runpy
import shutil
import subprocess
from pathlib import Path
import pytest
from autobookkeeping.archive import Archive, sha
from autobookkeeping.dashboard import projection, html, public_day, public_number

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=runpy.run_path(str(ROOT/"scripts/build_bookkeeping_dashboard.py"))


def row():
    return {"id":"opaque-1","kind":"invoice","source":"invoiz","date":"2011-01-02","status":"paid",
            "number":"0001","gross":"119.00","net":"100.00","vat":"19.00","vat_rate":19,"year":"2011",
            "coverage":"complete","documents":[],"source_detail":{"payments":[{"id":1,"type":"payment","amount":119,"date":"2011-01-03T12:00:00Z"}]},
            "buyer":{"name":"PRIVATE <script>SECRET</script>"},"description":"PRIVATE PRODUCT", "order_id":"PRIVATE ORDER"}


@pytest.fixture
def staged_repo(tmp_path):
    repo=tmp_path/"repo";repo.mkdir()
    def git(*args):return subprocess.check_output(["git","-C",str(repo),*args],stderr=subprocess.PIPE)
    git("init");git("config","user.name","Synthetic Test");git("config","user.email","test@example.invalid");git("config","core.autocrlf","false")
    for name in SCRIPT["CODE"]:
        target=repo/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    (repo/".env").write_text("ENCRYPTION_PASSWORD=synthetic-password\n",encoding="utf8")
    archive=Archive(repo);archive.init();catalog=archive.catalog();catalog["records"]["opaque-1"]={"current":row(),"history":[]};archive.save_catalog(catalog)
    SCRIPT["build"](repo, tool=repo)
    git("add","buchhaltung","src","scripts","dashboard.html");git("commit","-m","Synthetic initial archive")
    return repo,archive,git


def test_staged_snapshot_ignores_unstaged_database_and_is_deterministic(staged_repo):
    repo,archive,git=staged_repo
    catalog=archive.catalog();catalog["records"]["opaque-1"]["current"]["gross"]="130.00";archive.save_catalog(catalog)
    git("add","buchhaltung")
    staged_digest=sha((archive.root/"database.json.enc").read_bytes())
    catalog["records"]["opaque-1"]["current"]["gross"]="999.00";archive.save_catalog(catalog)
    SCRIPT["build"](repo,tool=repo,staged=True)
    snapshot=json.loads((repo/"dashboard.html").read_text(encoding="utf8").split('<script id="bookkeeping-data" type="application/json">')[1].split('</script>')[0])
    assert snapshot["source_sha256"]==staged_digest and snapshot["rows"][0]["gross_cents"]==13000
    first=(repo/"dashboard.html").read_bytes();SCRIPT["build"](repo,tool=repo,staged=True,check=True)
    assert (repo/"dashboard.html").read_bytes()==first
    assert git("diff","--name-only","--","buchhaltung").strip()


def test_incomplete_index_plaintext_and_manual_html_are_blocked(staged_repo):
    repo,archive,git=staged_repo
    archive.write("2011/Rechnungen/new.pdf.enc",b"%PDF-1.4 PRIVATE")
    git("add","buchhaltung/2011")
    with pytest.raises(ValueError,match="inventarisiert"):SCRIPT["build"](repo,tool=repo,staged=True)
    git("reset","--","buchhaltung/2011")
    (archive.root/"2011/Rechnungen/new.pdf.enc").unlink()
    (archive.root/"oops.pdf").write_bytes(b"PRIVATE PDF");git("add","buchhaltung/oops.pdf")
    with pytest.raises(ValueError,match="Klartextbeleg"):SCRIPT["build"](repo,tool=repo,staged=True)
    git("reset","--","buchhaltung/oops.pdf")
    (archive.root/"oops.pdf").unlink()
    catalog=archive.catalog();catalog["records"]["opaque-1"]["current"]["gross"]="130.00";archive.save_catalog(catalog)
    git("add","buchhaltung/database.json.enc","buchhaltung/manifest.json")
    (repo/"dashboard.html").write_text("USER EDIT",encoding="utf8")
    with pytest.raises(ValueError,match="überschrieben"):SCRIPT["build"](repo,tool=repo,staged=True)
    assert (repo/"dashboard.html").read_text()=="USER EDIT"


def test_partial_generator_edits_and_secret_staging_blocked(staged_repo):
    repo,archive,git=staged_repo
    helper=repo/"scripts/dashboard_view.html";helper.write_bytes(helper.read_bytes()+b'\n<!-- local edit -->')
    git("add","dashboard.html")
    # Force checking even when the index has no financial changes.
    with pytest.raises(ValueError,match="nicht vorgemerkte"):SCRIPT["build"](repo,tool=repo,staged=True,check=True)
    git("add",".env")
    with pytest.raises(ValueError,match="Passwort"):SCRIPT["build"](repo,tool=repo,staged=True)


def test_projection_and_script_injection_have_no_personal_fields():
    source=row();source.update(number='</script><script>PRIVATE_NUMBER</script>',date="PRIVATE DATE")
    catalog={"records":{"opaque-1":{"current":source,"history":[]}},"documents":{}}
    snapshot=projection(catalog,"0"*64);data=html(snapshot,(ROOT/"scripts/dashboard_view.html").read_bytes())
    assert b"PRIVATE" not in data and b"SECRET" not in data and b"source_detail" not in data
    assert snapshot["rows"][0]["number"] is None and snapshot["rows"][0]["date"] is None
    assert public_number("0901-K2")=="0901-K2" and public_day("2011-02-31") is None
    assert b"fetch(" not in data and b"https://" not in data and b"http://" not in data


def test_unknown_amount_not_silently_zero_and_trial_excluded():
    source=row();source.update(gross=None,net=None,vat=None)
    draft=dict(row(),id="draft",status="test_draft",gross="9999.00", revision="0"*64)
    catalog={"records":{"opaque-1":{"current":source,"history":[]}},"local_invoice_drafts":{"draft":{"current":draft,"history":[]}}}
    rows=projection(catalog,"0"*64)["rows"]
    assert next(r for r in rows if r["kind"]=="invoice")["gross_cents"] is None
    test=next(r for r in rows if r["kind"]=="draft");assert test["document_effect_cents"]==0 and test["flows"]==[]


def test_local_invoice_draft_without_kind_or_source_has_completion_number():
    draft = dict(row(), id="private-draft", status="test_draft", number=None, revision="0"*64)
    del draft["kind"]; del draft["source"]
    catalog = {"records": {}, "local_invoice_settings": {"last_service_number": "0900", "mode": "trial"},
               "local_invoice_drafts": {"private-draft": {"current": draft, "history": []}}}
    snapshot = projection(catalog, "0"*64); public = snapshot["rows"][0]
    assert public["proposed_number"] == "0901" and public["document_type"] == "invoice"
    assert snapshot["homeoffice_default_days"] == 210
    assert "private-draft" not in json.dumps(snapshot)
