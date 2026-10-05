"""Allowlisted financial projection, embedded HTML and staged-index verification."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path

from autobookkeeping.archive import Archive, encoded, sha, unseal, unwrap_key
from autobookkeeping.cashflow import cents, document_flows
from autobookkeeping.adjustments import fully_cancelled
from autobookkeeping.receipts import CATEGORIES
from autobookkeeping.homeoffice import public_allowances, DEFAULT_DAYS


PUBLIC_ROW_KEYS={"ref","date","kind","number","proposed_number","document_type","related_number","status","gross_cents","net_cents","vat_cents",
                 "vat_rates","tax_treatment","expense_category","coverage","source","flows","warnings","document_effect_cents"}
PUBLIC_FLOW_KEYS={"ref","date","amount_cents","bucket","origin"}


def public_number(value):
    value=str(value or "")
    return value if re.fullmatch(r"\d+(?:-K\d+)?",value) else None


def public_day(value):
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


def projection(catalog: dict, source_digest: str) -> dict:
    rows=[]
    values=[("records", v["current"]) for v in catalog["records"].values()]
    values += [(section, v["current"]) for section in ("local_invoice_drafts","local_adjustment_drafts","local_expense_drafts")
               for v in catalog.get(section,{}).values() if v["current"]["status"]=="test_draft"]
    for section, row in values:
        rid=row["id"];kind=row["kind"] if row["status"]!="test_draft" else "draft"
        proposal = None
        if section == "local_invoice_drafts":
            from autobookkeeping.local_invoices import LocalInvoices
            proposal = LocalInvoices.summary(row, catalog)["proposed_number"]
        elif section == "local_adjustment_drafts":
            from autobookkeeping.adjustments import Adjustments
            proposal = Adjustments.summary(row, catalog)["proposed_number"]
        if kind not in ("invoice", "expense", "credit_note", "correction", "draft"):
            raise ValueError("Unbekannte Belegart im Dashboard")
        if row.get("currency", "EUR") != "EUR":
            raise ValueError("Fremdwährungsbestand benötigt eine gesonderte Auswertung")
        status=row["status"]
        if kind=="invoice" and fully_cancelled(catalog,rid):
            status="locally_cancelled"
        elif kind=="invoice" and any(v["current"].get("original_id")==rid and v["current"].get("kind")=="credit_note" for v in catalog["records"].values()):
            status="partially_credited"
        flows,warnings=document_flows(catalog,row) if kind!="draft" else ([],["Ausgabenbeleg nur vorgemerkt; keine Ausgabe gebucht"] if row.get("kind")=="expense" else ["Testentwurf: keine Ausstellung oder Zahlung gebucht"])
        if row.get("tax_review_required"):
            warnings.append("Steuerliche Zuordnung des Ausgabenbelegs noch zu prüfen")
        if row.get("business_use") in ("mixed", "unclear"):
            warnings.append("Betrieblicher/privater Anteil noch gesondert zuzuordnen")
        def monetary(field):
            try:
                return cents(row[field]) if row.get(field) is not None else None
            except (ValueError,ArithmeticError):
                warnings.append("Belegbetrag unvollständig");return None
        gross=monetary("gross"); effect=gross
        if kind in ("draft","correction") or (kind=="invoice" and row["status"] in ("cancelled","draft")):
            effect=0
        rates=row.get("vat_rates") or ([row["vat_rate"]] if row.get("vat_rate") is not None else []) or sorted({g["vat_rate"] for g in row.get("vat_breakdown",[]) if type(g.get("vat_rate")) in (int,float)})
        exempt = kind in ("invoice", "credit_note", "draft") and (row.get("small_business") is True or (row.get("source_detail") or {}).get("smallBusiness") is True)
        tax_treatment = "small_business_exempt" if exempt else "domestic_vat" if row.get("tax_treatment")=="domestic_vat" else "source_unspecified"
        if row.get("coverage")!="complete" and kind!="draft":
            warnings.append("Originalbeleg fehlt")
        # No free text, buyer, supplier, product, external IDs, order/tracking, filenames or source blobs.
        result={"ref":sha(rid.encode())[:20],"date":public_day(row.get("date")),
                "kind":kind,"number":public_number(row.get("document_number") or row.get("number")),
                "proposed_number":public_number(proposal),
                "document_type":row.get("document_type") if row.get("document_type") in ("invoice","cancellation","partial_refund","correction","expense") else "invoice" if section == "local_invoice_drafts" else kind,
                "related_number":public_number(row.get("original_number")),"status":status if status in
                    ("paid","issued","recorded","cancelled","locally_cancelled","partially_credited","test_draft","draft") else "other",
                "gross_cents":gross,"net_cents":monetary("net"),"vat_cents":monetary("vat"),
                "vat_rates":[float(r) for r in rates if isinstance(r,(int,float)) and 0<=r<=100],
                "tax_treatment":tax_treatment,
                "expense_category":row.get("category") if row.get("kind")=="expense" and row.get("category") in CATEGORIES else None,
                "coverage":"complete" if row.get("coverage")=="complete" or kind=="draft" else "missing",
                "source":"local" if row.get("source")=="local" else "imported",
                "flows":flows,"warnings":sorted(set(warnings)),"document_effect_cents":effect}
        if set(result)!=PUBLIC_ROW_KEYS or any(set(flow)!=PUBLIC_FLOW_KEYS for flow in flows):
            raise ValueError("Dashboard-Schema überschreitet freigegebene Felder")
        rows.append(result)
    rows.sort(key=lambda r:(r["date"] or "",r["ref"]))
    return {"schema_version":1,"source_sha256":source_digest,"timezone":"Europe/Berlin","currency":"EUR",
            "basis":"Erfasste Zahlungsbewegungen; Belegbeträge getrennt. Arbeitsübersicht, keine vollständige steuerliche EÜR.",
            "gaps":["eBay-Abrechnungen, Gebühren und tatsächliche Verfügbarkeit abgleichen",
                    "Warenzugänge/Vine, Privatentnahmen und weitere Betriebseinnahmen/-ausgaben ergänzen",
                    "Anlagevermögen/AfA, Steuerzahlungen und Ausnahmen am Jahreswechsel gesondert zuordnen"],"rows":rows,
            "homeoffice": public_allowances(catalog), "homeoffice_default_days": DEFAULT_DAYS,
            "local_workflow_mode": catalog.get("local_invoice_settings", {}).get("mode", "unconfigured")
                if catalog.get("local_invoice_settings", {}).get("mode", "unconfigured") in ("local", "trial", "unconfigured") else "unconfigured"}


def html(snapshot: dict, template: bytes) -> bytes:
    marker=b"__BOOKKEEPING_DATA__"
    if template.count(marker)!=1:
        raise ValueError("Dashboard-Vorlage hat keinen eindeutigen Datenplatzhalter")
    payload=json.dumps(snapshot,ensure_ascii=False,separators=(",",":"),allow_nan=False)
    for char,escaped in (("<","\\u003c"),(">","\\u003e"),("&","\\u0026"),("\u2028","\\u2028"),("\u2029","\\u2029")):
        payload=payload.replace(char,escaped)
    return template.replace(marker,payload.encode("utf-8"))


def index_blob(repo:Path,name:str)->bytes:
    return subprocess.check_output(["git","-C",str(repo),"show",":"+name],stderr=subprocess.PIPE)


def index_catalog(repo:Path)->tuple[dict,str]:
    archive=Archive(repo)
    key=unwrap_key(index_blob(repo,"buchhaltung/key.json"),archive.password)
    database=index_blob(repo,"buchhaltung/database.json.enc")
    catalog=json.loads(unseal(key,database,"database.json.enc"))
    manifest=json.loads(index_blob(repo,"buchhaltung/manifest.json"))
    inventory=subprocess.check_output(["git","-C",str(repo),"ls-files","-z","--","buchhaltung"]).decode().split("\0")
    actual=set()
    for path in filter(None,inventory):
        name=path.removeprefix("buchhaltung/")
        if name in ("README.md","AGENTS.md","manifest.json") or re.fullmatch(r"nachweise/[a-f0-9]{40}(?:[a-f0-9]{24})?\.json(?:\.ots(?:\.bak)?)?",name):
            continue
        if name=="key.json" or name.endswith(".enc"):
            actual.add(name)
        else:
            raise ValueError("Unerlaubter Klartextbeleg im Git-Index der Buchhaltung")
    if actual!=set(manifest["files"]) or actual-{"key.json","database.json.enc"}!=set(catalog["documents"]):
        raise ValueError("Gestagter Dokumentbestand ist nicht vollständig inventarisiert")
    # One git process for all binary blobs, rather than hundreds of Windows subprocesses.
    names=sorted(actual)
    batch=subprocess.run(["git","-C",str(repo),"cat-file","--batch"],
                         input="".join(":buchhaltung/"+n+"\n" for n in names).encode(),capture_output=True,check=True).stdout
    offset=0
    for name in names:
        end=batch.index(b"\n",offset);header=batch[offset:end].split()
        if len(header)!=3 or header[1]!=b"blob":
            raise ValueError("Gestagter Beleg ist kein Blob")
        size=int(header[2]);data=batch[end+1:end+1+size];offset=end+size+2
        expected=manifest["files"][name]
        if size!=expected["bytes"] or sha(data)!=expected["sha256"]:
            raise ValueError("Gestagter Beleg stimmt nicht mit Manifest überein")
        if name in catalog["documents"]:
            original=unseal(key,data,name);metadata=catalog["documents"][name]
            if sha(original)!=metadata["sha256_plaintext"] or len(original)!=metadata["bytes_plaintext"]:
                raise ValueError("Gestagter Originalbeleg stimmt nicht mit verschlüsselter Datenbank überein")
    for section in ("records","local_invoice_drafts","local_adjustment_drafts","local_expense_drafts"):
        for value in catalog.get(section,{}).values():
            for row in [value["current"],*value["history"]]:
                if any(name not in catalog["documents"] for name in row["documents"]):
                    raise ValueError("Gestagter Datensatz verweist auf fehlenden Originalbeleg")
    from autobookkeeping.ledger_validation import validate
    validate(catalog)
    return catalog,sha(database)
