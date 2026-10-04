import copy
import json
from pathlib import Path

import pytest
from autobookkeeping.archive import Archive, encoded
from autobookkeeping.dashboard import projection, html
from autobookkeeping.homeoffice import calculate, record, eur_summary
from autobookkeeping.ledger_validation import validate
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError


@pytest.mark.parametrize("days,amount", [(0, 0), (1, 600), (120, 72000), (210, 126000), (211, 126000), (365, 126000)])
def test_daily_rate_and_annual_cap(days, amount):
    assert calculate(2026, days)["amount_cents"] == amount


@pytest.mark.parametrize("year,days,other", [(2022, 1, "0"), (2027, 1, "0"), (2026, -1, "0"),
    (2026, 366, "0"), (2026, 1.5, "0"), (2026, True, "0"), (2026, 1, "1260.01"), (2026, 1, "0.001")])
def test_invalid_days_years_and_other_claims(year, days, other):
    with pytest.raises(WorkflowError): calculate(year, days, other)


def test_leap_year_and_shared_limit():
    assert calculate(2024, 366)["amount_cents"] == 126000
    assert calculate(2026, 210, "600.00")["amount_cents"] == 66000
    assert calculate(2026, 1, "1259.00")["amount_cents"] == 100


@pytest.fixture
def workflow(tmp_path):
    repo = tmp_path / "repo"; repo.mkdir()
    archive = Archive(repo, "synthetic-password"); archive.init()
    return LocalInvoices(archive)


def test_approval_encryption_replacement_history_and_no_cash(workflow):
    archive = workflow.archive; basis = "PRIVATE HOME WORKING DAYS NOTE"
    with pytest.raises(WorkflowError): record(workflow, 2026, 120, basis, True, False)
    with pytest.raises(WorkflowError): record(workflow, 2026, 120, basis, False, True)
    assert not archive.catalog().get("homeoffice_allowances")
    assert record(workflow, 2026, 120, basis, True, True)["changed"]
    cipher = (archive.root / "database.json.enc").read_bytes()
    assert basis.encode() not in cipher and not archive.catalog()["records"]
    assert not record(workflow, 2026, 120, basis, True, True)["changed"]
    assert (archive.root / "database.json.enc").read_bytes() == cipher
    record(workflow, 2026, 150, basis, True, True)
    entry = archive.catalog()["homeoffice_allowances"]["2026"]
    assert len(entry["history"]) == 1 and entry["current"]["amount_cents"] == 90000
    assert archive.verify()["ok"] and not archive.catalog().get("cash_events")
    public = projection(archive.catalog(), "0" * 64)
    assert public["homeoffice"][0]["days"] == 150 and public["rows"] == []
    assert basis not in json.dumps(public) and "eligibility_confirmed" not in json.dumps(public)
    assert eur_summary(archive.catalog(), 2026)["cash_surplus_cents"] == 0
    assert eur_summary(archive.catalog(), 2026)["eur_working_surplus_cents"] == -90000
    assert archive.report("2026")["2026"]["expenses"] == 0
    assert archive.report("2026")["2026"]["eur_working"]["homeoffice_cents"] == 90000
    record(workflow, 2026, 0, "Explicit corrected year total", True, True)
    assert eur_summary(archive.catalog(), 2026)["homeoffice_cents"] == 0
    assert len(archive.catalog()["homeoffice_allowances"]["2026"]["history"]) == 2


def test_annual_reporting_by_payment_year_and_no_double_expense(workflow):
    archive = workflow.archive; catalog = archive.catalog()
    catalog["records"] = {
        "income": {"current": {"id": "income", "kind": "invoice", "source": "invoiz", "year": "2025",
            "status": "paid", "gross": "1000.00", "net": "1000.00", "vat": "0.00", "documents": [], "coverage": "complete",
            "source_detail": {"payments": [{"id": 1, "type": "payment", "amount": "1000.00", "date": "2026-01-01"}]}}, "history": []},
        "expense": {"current": {"id": "expense", "kind": "expense", "year": "2026", "status": "recorded", "gross": "100.00",
            "net": "100.00", "vat": "0.00", "pay_date": "2026-02-01", "documents": [], "coverage": "complete"}, "history": []}}
    archive.save_catalog(catalog)
    record(workflow, 2026, 100, "PRIVATE DAYS BASIS 2026", True, True)
    record(workflow, 2025, 10, "PRIVATE DAYS BASIS 2025", True, True)
    report = eur_summary(archive.catalog(), 2026)
    assert report["income_cents"] == 100000 and report["cash_expenses_cents"] == 10000
    assert report["homeoffice_cents"] == 60000 and report["expense_total_with_homeoffice_cents"] == 70000
    assert report["cash_surplus_cents"] == 90000 and report["eur_working_surplus_cents"] == 30000
    assert eur_summary(archive.catalog(), 2025)["eur_working_surplus_cents"] == -6000
    assert eur_summary(archive.catalog())["homeoffice_cents"] == 66000


def test_tampered_amount_or_history_cannot_pass_integrity_check(workflow):
    record(workflow, 2026, 100, "Synthetic eligibility evidence", True, True)
    catalog = copy.deepcopy(workflow.archive.catalog())
    catalog["homeoffice_allowances"]["2026"]["current"]["amount_cents"] = 126000
    with pytest.raises(ValueError): validate(catalog)


def test_interrupted_annual_change_recovers_without_double_counting(workflow, monkeypatch):
    archive = workflow.archive; original_save = archive.save_catalog
    def power_loss(catalog): raise OSError("Synthetic interruption")
    monkeypatch.setattr(archive, "save_catalog", power_loss)
    with pytest.raises(OSError): record(workflow, 2026, 100, "PRIVATE DAYS EVIDENCE", True, True)
    assert workflow.journal.exists() and b"PRIVATE DAYS EVIDENCE" not in workflow.journal.read_bytes()
    monkeypatch.setattr(archive, "save_catalog", original_save)
    workflow.recover()
    assert not record(workflow, 2026, 100, "PRIVATE DAYS EVIDENCE", True, True)["changed"]
    assert eur_summary(archive.catalog(), 2026)["homeoffice_cents"] == 60000
