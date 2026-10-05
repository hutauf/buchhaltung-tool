"""Linked, immutable cancellations, partial credits and non-monetary corrections.

No document authorizes or executes a refund. Actual money is a separate cash event.
"""
from __future__ import annotations

import copy
import re
import uuid
from datetime import date
from decimal import Decimal

from autobookkeeping.archive import encoded, sha
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError, number_state, render_pdf, today, now
from autobookkeeping.taxes import decimal_money


def credits(catalog: dict, invoice_id: str) -> list[dict]:
    return [v["current"] for v in catalog["records"].values()
            if v["current"].get("kind") == "credit_note" and v["current"].get("original_id") == invoice_id]


def fully_cancelled(catalog: dict, invoice_id: str) -> bool:
    row = catalog["records"].get(invoice_id, {}).get("current", {})
    documents = credits(catalog, invoice_id)
    return (any(r.get("document_type") == "cancellation" for r in documents)
            and sum((Decimal(r["gross"]) for r in documents), Decimal(0)) == -Decimal(row.get("gross", 0)))


def original_view(catalog: dict, invoice_id: str) -> dict:
    row = copy.deepcopy(catalog["records"][invoice_id]["current"])
    if row["kind"] != "invoice" or row["status"] not in ("issued", "paid") or not row.get("number"):
        raise WorkflowError("Nur ausgestellte, noch nicht im Quellsystem stornierte Originalrechnungen verwenden")
    if row.get("currency", "EUR") != "EUR":
        raise WorkflowError("Rechnungskorrekturen derzeit nur in EUR")
    if row.get("source") != "local" and not row.get("positions"):
        detail = row.get("source_detail")
        if not detail:
            raise WorkflowError("Vollständige Originalpositionen zuerst importieren")
        customer = detail["customerData"]
        if customer.get("countryIso", "DE") != "DE":
            raise WorkflowError("Auslandsfälle benötigen eine gesonderte steuerliche Prüfung")
        positions = []
        for p in detail["positions"]:
            gross = decimal_money(p["totalGrossAfterDiscount"]); net = decimal_money(p["totalNetAfterDiscount"])
            positions.append({"title": p["title"], "quantity": p["amount"], "unit": p.get("unit", "Stk."),
                              "unit_gross": str(decimal_money(p["priceGrossAfterDiscount"])), "gross": str(gross),
                              "net": str(net), "vat": str(gross-net), "vat_rate": p["vatPercent"]})
        row.update(seller=copy.deepcopy(catalog["local_invoice_settings"]["seller"]),
                   buyer={"name": customer["name"], "street": customer["street"], "postal_code": customer["zipCode"],
                          "city": customer["city"], "country": "Deutschland", "country_iso": "DE"},
                   positions=positions, small_business=detail["smallBusiness"],
                   order_id=customer.get("number") or "Originalbezug " + str(row["number"]),
                   delivery_date=(detail.get("deliveryDate") or detail["date"])[:10])
    # Original source amounts, including discounts, must reconcile; never reconstruct silently.
    for field in ("gross", "net", "vat"):
        if sum((Decimal(p[field]) for p in row["positions"]), Decimal(0)) != Decimal(row[field]):
            raise WorkflowError("Originalpositionen und Gesamtbetrag stimmen nicht überein")
    if not row.get("small_business") and any(p["vat_rate"] not in (7, 19) for p in row["positions"]):
        raise WorkflowError("Steuerfall der Originalrechnung wird noch nicht unterstützt")
    previous = [v["current"] for v in catalog["records"].values()
                if v["current"].get("kind") == "correction" and v["current"].get("original_id") == invoice_id]
    if previous:
        effective = max(previous, key=lambda r:r["correction_sequence"])
        row["buyer"] = copy.deepcopy(effective["buyer"])
        row["delivery_date"] = effective["delivery_date"]
    return row


def context_hash(catalog: dict, invoice_id: str) -> str:
    related = [v["current"] for v in catalog["records"].values()
               if v["current"].get("original_id") == invoice_id]
    return sha(encoded({"original": catalog["records"][invoice_id]["current"], "related": sorted(related, key=lambda r:r["id"])}))


def remaining_positions(catalog: dict, original: dict) -> list[dict]:
    remaining = [{field: Decimal(p[field]) for field in ("gross", "net", "vat")} for p in original["positions"]]
    for credit in credits(catalog, original["id"]):
        for position in credit["positions"]:
            for field in ("gross", "net", "vat"):
                remaining[position["original_position_index"]][field] += Decimal(position[field])
    if any(p["gross"] < 0 or p["net"] < 0 or p["vat"] < 0 or p["gross"] != p["net"] + p["vat"] for p in remaining):
        raise WorkflowError("Bestehende Minderungen übersteigen das Original")
    return remaining


class Adjustments:
    def __init__(self, workflow: LocalInvoices):
        self.workflow = workflow
        self.archive = workflow.archive

    def prepare(self, invoice_id: str, action: str, payload: dict) -> dict:
        if action not in ("cancellation", "partial_refund", "correction"):
            raise WorkflowError("Unbekannte Korrekturart")
        if not isinstance(payload.get("reason"), str) or not payload["reason"].strip():
            raise WorkflowError("Nachvollziehbarer Korrekturgrund erforderlich")
        self.archive.verify()
        before = self.archive.catalog(); after = copy.deepcopy(before)
        original = original_view(after, invoice_id)
        if fully_cancelled(after, invoice_id):
            raise WorkflowError("Original wurde bereits vollständig storniert")
        draft = copy.deepcopy(original)
        draft.update(id="local-adjustment-draft:" + uuid.uuid4().hex, status="test_draft", number=None,
                     kind="correction" if action == "correction" else "credit_note", document_type=action,
                     original_id=invoice_id, original_number=original["number"], original_date=original["date"][:10],
                     original_context_sha256=context_hash(after, invoice_id), reason=payload["reason"].strip(),
                     date=today(), year=today()[:4], created_at=now(), request=payload)
        if action == "correction":
            self._correct(after, original, draft, payload)
        else:
            self._credit(after, original, draft, payload, action)
        comparable = {k:v for k,v in draft.items() if k not in ("id", "created_at", "documents")}
        for value in after.get("local_adjustment_drafts", {}).values():
            prior = value["current"]
            if prior["status"] == "test_draft" and prior.get("request_sha256") == sha(encoded(comparable)):
                return self.summary(prior, after)
        draft["request_sha256"] = sha(encoded(comparable))
        pdf = render_pdf(draft, draft=True)
        name = f"{draft['year']}/Rechnungen/{sha((draft['id'] + ':' + sha(pdf)).encode())}.pdf.enc"
        draft["documents"] = [name]; draft["revision"] = sha(encoded(draft))
        after["documents"][name] = {"record_id":draft["id"], "role":"adjustment_test_draft",
                                    "sha256_plaintext":sha(pdf), "bytes_plaintext":len(pdf)}
        after.setdefault("local_adjustment_drafts", {})[draft["id"]] = {"current":draft, "history":[]}
        self.workflow.commit(before, after, {name:pdf})
        return self.summary(draft, after)

    def _correct(self, catalog, original, draft, payload):
        changes = payload.get("changes")
        if not isinstance(changes, dict) or not changes:
            raise WorkflowError("Konkrete Berichtigungsfelder erforderlich")
        previous = [v["current"] for v in catalog["records"].values()
                    if v["current"].get("kind") == "correction" and v["current"].get("original_id") == original["id"]]
        effective = copy.deepcopy(original)
        if previous:
            effective = max(previous, key=lambda r:r["correction_sequence"])
            draft["buyer"] = copy.deepcopy(effective["buyer"])
            draft["delivery_date"] = effective["delivery_date"]
        labels = {"buyer.name":"Empfängername", "buyer.street":"Empfängeranschrift", "buyer.postal_code":"Postleitzahl",
                  "buyer.city":"Ort", "delivery_date":"Lieferdatum"}
        correction_changes = []
        for key, value in changes.items():
            if key not in labels or not isinstance(value, str) or not value.strip():
                raise WorkflowError("Nur Name, inländische Anschrift und Lieferdatum berichtigen; Betrag/Steuer über Storno und Ersatzrechnung")
            if key == "delivery_date":
                date.fromisoformat(value); old = effective.get(key); draft[key] = value
            else:
                field = key.split(".")[1]; old = effective["buyer"][field]; draft["buyer"][field] = value
                if field == "postal_code" and not re.fullmatch(r"\d{5}", value):
                    raise WorkflowError("Berichtigte Postleitzahl muss fünfstellig sein")
            if old != value:
                correction_changes.append({"label":labels[key], "before":old, "after":value})
        if not correction_changes:
            raise WorkflowError("Berichtigung enthält keine Änderung")
        draft.update(gross="0.00", net="0.00", vat="0.00", correction_changes=correction_changes,
                     correction_sequence=len(previous)+1, positions=[])

    def _credit(self, catalog, original, draft, payload, action):
        remaining = remaining_positions(catalog, original)
        if action == "cancellation":
            allocations = [{"position_index":i, "gross":str(p["gross"])} for i,p in enumerate(remaining) if p["gross"]]
        else:
            allocations = payload.get("allocations")
            if not isinstance(allocations,list) or not allocations:
                raise WorkflowError("Teilbetrag eindeutig auf Originalpositionen verteilen")
        positions = []; seen=set()
        for allocation in allocations:
            index = allocation["position_index"]
            if not isinstance(index,int) or isinstance(index,bool) or not 0 <= index < len(remaining) or index in seen:
                raise WorkflowError("Originalpositionsindex fehlt, ist doppelt oder ungültig")
            seen.add(index); value = decimal_money(allocation["gross"]); balance = remaining[index]
            if value <= 0 or value > balance["gross"]:
                raise WorkflowError("Erstattungsbetrag muss positiv sein und innerhalb des verbleibenden Originalbetrags liegen")
            p = original["positions"][index]
            if value == balance["gross"]:
                net, vat = balance["net"], balance["vat"]
            else:
                net = decimal_money(value * Decimal(p["net"]) / Decimal(p["gross"]))
                vat = value - net
                if net > balance["net"] or vat > balance["vat"]:
                    raise WorkflowError("Teilbetrag führt zu inkonsistenter Steuer-Rundung; Aufteilung prüfen")
            positions.append({"title":p["title"], "quantity":1, "unit":"Betrag", "unit_gross":str(-value),
                              "gross":str(-value), "net":str(-net), "vat":str(-vat), "vat_rate":p["vat_rate"],
                              "original_position_index":index})
        groups={}
        for p in positions:
            group=groups.setdefault(p["vat_rate"], {field:Decimal(0) for field in ("gross","net","vat")})
            for field in group:
                group[field]+=Decimal(p[field])
        draft.update(positions=positions, **{field:str(sum((Decimal(p[field]) for p in positions),Decimal(0)).quantize(Decimal("0.01")))
                                            for field in ("gross","net","vat")},
                     vat_breakdown=[dict(vat_rate=rate,**{k:str(v) for k,v in values.items()}) for rate,values in sorted(groups.items())])

    @staticmethod
    def summary(row, catalog):
        last,width=number_state(catalog)
        proposal = f"{row['original_number']}-K{row['correction_sequence']}" if row["kind"]=="correction" else str(last+1).zfill(width)
        return {"id":row["id"], "status":row["status"], "kind":row["document_type"], "original_number":row["original_number"],
                "gross":row["gross"], "revision":row["revision"], "proposed_number":proposal if row["status"]=="test_draft" else None,
                "number":row.get("document_number") or row["number"], "documents":row["documents"]}

    def issue(self, draft_id, revision, expected_number, approved):
        if not approved:
            raise WorkflowError("Korrekturabschluss benötigt Freigabe des konkreten Dokuments")
        self.archive.verify(); before=self.archive.catalog(); after=copy.deepcopy(before)
        if after["local_invoice_settings"]["mode"] != "local":
            raise WorkflowError("Probebetrieb: Korrekturen nur als Testentwurf")
        value=after["local_adjustment_drafts"][draft_id]; draft=value["current"]
        if draft["status"]!="test_draft" or draft["revision"]!=revision:
            raise WorkflowError("Korrekturentwurf wurde geändert oder bereits abgeschlossen")
        if context_hash(after,draft["original_id"])!=draft["original_context_sha256"]:
            raise WorkflowError("Original/Korrekturstand wurde verändert; Korrekturentwurf erneut prüfen")
        proposal=self.summary(draft,after)["proposed_number"]
        if expected_number != proposal:
            raise WorkflowError("Korrektur-Belegnummer wurde seit der Prüfung verändert")
        row=copy.deepcopy(draft)
        row.update(id="local:"+draft["kind"]+":"+draft_id.split(":")[-1],source="local",source_id=draft_id.split(":")[-1],
                   number=proposal if draft["kind"]=="credit_note" else None, document_number=proposal,
                   status="issued", date=today(),year=today()[:4],issued_at=now(),coverage="complete",cash_effect="not_recorded")
        pdf=render_pdf(row,draft=False)
        name=f"{row['year']}/Rechnungen/{sha((row['id']+':'+sha(pdf)).encode())}.pdf.enc"
        row["documents"]=[name];row["revision"]=sha(encoded(row))
        after["documents"][name]={"record_id":row["id"],"role":row["kind"],"sha256_plaintext":sha(pdf),"bytes_plaintext":len(pdf)}
        after["records"][row["id"]]={"current":row,"history":[]}
        value["history"].append(copy.deepcopy(draft));value["current"]=dict(draft,status="issued",number=row["number"],document_number=proposal,invoice_id=row["id"],documents=[name])
        after.setdefault("local_events",[]).append({"action":row["document_type"],"record_id":row["id"],"original_id":row["original_id"],"at":now()})
        self.workflow.commit(before,after,{name:pdf})
        return {"ok":True,"id":row["id"],"number":proposal,"original_number":row["original_number"],"gross":row["gross"],"refund_executed":False}


def change_tax_profile(workflow, small_business, reason, approved):
    if not approved or not isinstance(reason,str) or not reason.strip():
        raise WorkflowError("Steuerprofilwechsel benötigt ausdrückliche Freigabe und geprüften Grund")
    workflow.archive.verify(); before=workflow.archive.catalog(); after=copy.deepcopy(before)
    old=after["local_invoice_settings"]["seller"]["small_business"]
    if old==small_business:
        raise WorkflowError("Steuerprofil ist bereits so eingestellt")
    after["local_invoice_settings"]["seller"]["small_business"]=small_business
    after.setdefault("local_events",[]).append({"action":"tax_profile","before":old,"after":small_business,"reason":reason,"at":now()})
    workflow.commit(before,after,{})
    return {"ok":True,"small_business":small_business,"existing_documents_unchanged":True}
