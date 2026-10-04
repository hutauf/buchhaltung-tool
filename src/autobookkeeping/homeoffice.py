"""Annual non-cash EÜR deduction, separate from supplier expenses/payments."""
from __future__ import annotations

import calendar
import copy
from decimal import Decimal

from autobookkeeping.local_invoices import WorkflowError, now
from autobookkeeping.taxes import decimal_money

LAW_URL = "https://www.gesetze-im-internet.de/estg/__4.html"
RULE_CHECKED_ON = "2026-10-04"
DEFAULT_DAYS = 210


def calculate(year: int, days: int, other_claimed="0.00") -> dict:
    # Only reviewed tax years; a later year requires checking the then-current law.
    if type(year) is not int or not 2023 <= year <= 2026:
        raise WorkflowError("Regelstand für 2023–2026 geprüft; anderes Jahr zuerst steuerlich prüfen")
    if type(days) is not int or not 0 <= days <= (366 if calendar.isleap(year) else 365):
        raise WorkflowError("Berechtigte Tage als ganze Zahl innerhalb des Kalenderjahrs angeben")
    other = decimal_money(other_claimed)
    if Decimal(str(other_claimed)) != other or not 0 <= other <= Decimal("1260.00"):
        raise WorkflowError("Anderweitig beanspruchte Tagespauschale als Centbetrag zwischen 0 und 1260 EUR angeben")
    available = 126000 - int(other * 100)
    amount = min(days * 600, available)
    return {"year": year, "days": days, "day_rate_cents": 600, "annual_cap_cents": 126000,
            "other_claimed_cents": int(other * 100), "amount_cents": amount, "capped": days * 600 > available}


def record(workflow, year, days, basis, eligible, approved, other_claimed="0.00"):
    if not approved or eligible is not True:
        raise WorkflowError("Konkrete Tageszahl/Betrag und steuerliche Berechtigung benötigen Freigabe")
    if not isinstance(basis, str) or not basis.strip():
        raise WorkflowError("Grundlage der Tageszählung und Ausschluss einer Doppelberücksichtigung dokumentieren")
    result = calculate(year, days, other_claimed)
    workflow.archive.verify(); before = workflow.archive.catalog(); after = copy.deepcopy(before)
    candidate = dict(result, eligibility_confirmed=True, basis=basis.strip(), law_url=LAW_URL, rule_checked_on=RULE_CHECKED_ON)
    section = after.setdefault("homeoffice_allowances", {})
    previous = section.get(str(year))
    if previous and {k: v for k, v in previous["current"].items() if k != "updated_at"} == candidate:
        return {"ok": True, "changed": False, **result}
    candidate["updated_at"] = now()
    section[str(year)] = {"current": candidate, "history": previous["history"] + [previous["current"]] if previous else []}
    workflow.commit(before, after, {})
    return {"ok": True, "changed": True, **result, "cash_payment": False, "vat": None}


def validate(catalog):
    for year, entry in catalog.get("homeoffice_allowances", {}).items():
        for row in [entry["current"], *entry["history"]]:
            expected = calculate(row["year"], row["days"], Decimal(row["other_claimed_cents"]) / 100)
            if str(row["year"]) != year or any(row.get(k) != v for k, v in expected.items()):
                raise ValueError("Homeoffice-Pauschale stimmt nicht mit Tagen/Jahreslimit überein")
            if row.get("eligibility_confirmed") is not True or not isinstance(row.get("basis"), str) or not row["basis"].strip():
                raise ValueError("Homeoffice-Nachweis/Berechtigung fehlt")


def public_allowances(catalog):
    validate(catalog)
    return [calculate(v["current"]["year"], v["current"]["days"], Decimal(v["current"]["other_claimed_cents"]) / 100)
            for _, v in sorted(catalog.get("homeoffice_allowances", {}).items())]


def eur_summary(catalog, year=None):
    from autobookkeeping.cashflow import document_flows
    income = expense = 0
    for value in catalog["records"].values():
        flows, _ = document_flows(catalog, value["current"])
        for flow in flows:
            if year is None or flow["date"].startswith(str(year) + "-"):
                if flow["bucket"] == "income": income += flow["amount_cents"]
                else: expense -= flow["amount_cents"]
    allowances = [r for r in public_allowances(catalog) if year is None or r["year"] == int(year)]
    deduction = sum(r["amount_cents"] for r in allowances)
    return {"income_cents": income, "cash_expenses_cents": expense, "homeoffice_cents": deduction,
            "expense_total_with_homeoffice_cents": expense + deduction, "cash_surplus_cents": income - expense,
            "eur_working_surplus_cents": income - expense - deduction}
