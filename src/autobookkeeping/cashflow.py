"""Payment-date working EÜR. Documents never stand in for actual repayments."""
from __future__ import annotations

import copy
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from autobookkeeping.archive import encoded, sha
from autobookkeeping.local_invoices import WorkflowError, now
from autobookkeeping.taxes import decimal_money


def payment_day(value) -> str:
    if not isinstance(value,str):
        raise ValueError("Zahlungsdatum fehlt")
    if len(value)==10:
        return date.fromisoformat(value).isoformat()
    value=datetime.fromisoformat(value.replace("Z","+00:00"))
    if value.tzinfo is None:
        raise ValueError("Zeitzone fehlt")
    return value.astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()


def cents(value) -> int:
    return int(decimal_money(value)*100)


def document_flows(catalog: dict, row: dict) -> tuple[list[dict], list[str]]:
    rid=row["id"]; flows=[]; warnings=[]
    def append(value, when, reference, origin, bucket):
        try:
            amount=cents(value); day=payment_day(when)
        except (ValueError, TypeError, ArithmeticError):
            warnings.append("Zahlungsdatum oder Betrag unvollständig")
            return
        flows.append({"ref":sha((rid+":"+str(reference)).encode())[:20],"date":day,
                      "amount_cents":amount,"bucket":bucket,"origin":origin})
    if rid in catalog.get("cash_source_overrides",{}):
        override=catalog["cash_source_overrides"][rid]
        for event_id,event in catalog.get("cash_events",{}).items():
            if event["record_id"]==rid and event_id not in catalog.get("cash_event_voids",{}):
                append(event["amount"],event["date"],event_id,"verified",event["bucket"])
        if not override["complete"]:
            warnings.append("Zahlungszuordnung noch nicht als vollständig bestätigt")
        return flows,warnings
    kind=row["kind"]
    if kind=="invoice":
        if row.get("source") != "local":
            detail=row.get("source_detail") or {}
            seen=set()
            for payment in detail.get("payments",[]):
                pid=payment.get("id")
                if pid is None or pid in seen or payment.get("type")!="payment":
                    warnings.append("Unklare oder doppelte Zahlung in Quelldaten")
                    continue
                seen.add(pid)
                append(payment.get("amount"),payment.get("date"),pid,"imported","income")
            if not flows:
                warnings.append("Kein verwertbarer Zahlungseintrag")
            if row.get("status")=="cancelled":
                warnings.append("Quell-Storno: tatsächliche Rückzahlung und separaten Beleg prüfen")
            if any(p.get("cancellationPaymentId") for p in detail.get("payments",[])):
                warnings.append("Quell-Zahlungsstorno/Umgebung: mit tatsächlichem Zahlungsfluss abgleichen")
        elif row.get("pay_date") and row.get("payment_status")=="paid" and not row.get("replacement_of"):
            append(row["gross"],row["pay_date"],"ebay-paid","ebay_paid","income")
            warnings.append("eBay-Käuferzahlung: Verfügbarkeit/Abrechnung noch abgleichen")
        else:
            warnings.append("Zahlungsnachweis fehlt; Ersatzrechnung erzeugt keinen neuen Geldeingang")
    elif kind=="expense":
        if row.get("pay_date"):
            append(-decimal_money(row.get("paid_amount") or row["gross"]),row["pay_date"],"expense-payment","source_pay_date","expense")
            if row.get("paid_amount") and decimal_money(row["paid_amount"]) < decimal_money(row["gross"]):
                warnings.append("Ausgabe erst teilweise bezahlt")
        else:
            warnings.append("Zahlungsdatum der Ausgabe fehlt")
    elif kind=="expense_credit":
        if row.get('pay_date'):
            append(decimal_money(row.get('paid_amount') or -Decimal(row['gross'])), row['pay_date'],
                   'supplier-refund','source_pay_date','expense')
            if Decimal(row.get('paid_amount') or -Decimal(row['gross'])) < abs(Decimal(row['gross'])):
                warnings.append('Lieferanten-Korrektur erst teilweise erstattet')
        else:
            warnings.append('Lieferanten-Korrektur ohne nachgewiesene Erstattung; kein Geldfluss')
    elif kind=="credit_note":
        warnings.append("Keine tatsächliche Zahlung/Erstattung zugeordnet; Minderungsbeleg allein bewegt kein Geld")
    return flows,warnings


def record_cash(workflow, payload: dict, approved: bool) -> dict:
    if not approved:
        raise WorkflowError("Zahlungszuordnung benötigt Freigabe von Beleg, Betrag, Datum und Nachweis")
    required={"record_id","amount","date","external_reference","evidence","source_complete"}
    if not required<=payload.keys() or not all(isinstance(payload[k],str) and payload[k].strip() for k in ("external_reference","evidence")):
        raise WorkflowError("Zahlungsquelle und konkreter Nachweis erforderlich")
    if type(payload["source_complete"]) is not bool:
        raise WorkflowError("Vollständigkeit der Zahlungsquelle ausdrücklich angeben")
    date.fromisoformat(payload["date"])
    if len(payload["date"])!=10:
        raise WorkflowError("Zahlungsdatum als ISO-Kalendertag angeben")
    amount=decimal_money(payload["amount"])
    if not amount:
        raise WorkflowError("Zahlungsbewegung darf nicht null sein")
    workflow.archive.verify();before=workflow.archive.catalog();after=copy.deepcopy(before)
    row=after["records"][payload["record_id"]]["current"]
    if row["kind"] not in ("invoice","expense","expense_credit","credit_note") or row.get("status") in ("draft","test_draft") or row.get("currency","EUR")!="EUR":
        raise WorkflowError("Zahlungszuordnung benötigt einen echten EUR-Beleg")
    if row.get("source")=="local" and row["kind"]=="invoice" and amount<0:
        raise WorkflowError("Lokale Rückzahlungen am verknüpften Minderungsbeleg erfassen; Zahlungsfehler mit cash-void berichtigen")
    eid="cash:"+sha(payload["external_reference"].encode())
    event=dict(payload,amount=str(amount),bucket="expense" if row["kind"] in ("expense","expense_credit") else "income")
    existing=after.get("cash_events",{}).get(eid)
    if existing:
        if {k:existing[k] for k in event}!=event or eid in after.get("cash_event_voids",{}):
            raise WorkflowError("Zahlungsreferenz wurde bereits anders verwendet oder berichtigt")
        return {"ok":True,"changed":False,"event_id":eid}
    previous=sum((Decimal(e["amount"]) for key,e in after.get("cash_events",{}).items()
                  if e["record_id"]==row["id"] and key not in after.get("cash_event_voids",{})),Decimal(0))
    total=previous+amount; limit=abs(Decimal(row["gross"]))
    if row["kind"]=="invoice" and not 0<=total<=limit:
        raise WorkflowError("Zahlungssumme liegt außerhalb des Rechnungsbetrags")
    if row["kind"]=="credit_note" and not -limit<=total<=0:
        raise WorkflowError("Rückzahlungssumme übersteigt den Minderungsbeleg")
    if row["kind"]=="expense" and not -limit<=total<=0:
        raise WorkflowError("Zahlungssumme liegt außerhalb des Ausgabenbelegs")
    if row['kind']=='expense_credit' and not 0<=total<=limit:
        raise WorkflowError('Lieferanten-Erstattung muss positiv sein und innerhalb der Korrektur liegen')
    if row['kind']=='expense_credit' and amount<0:
        raise WorkflowError('Lieferanten-Erstattung muss positiv sein; fehlerhafte Zuordnung berichtigen')
    event["recorded_at"]=now()
    after.setdefault("cash_events",{})[eid]=event
    after.setdefault("cash_source_overrides",{})[row["id"]]={"complete":payload["source_complete"],"updated_at":now()}
    workflow.commit(before,after,{})
    return {"ok":True,"changed":True,"event_id":eid,"source_entries_replaced":True}


def void_cash(workflow,event_id,reason,approved):
    if not approved or not isinstance(reason,str) or not reason.strip():
        raise WorkflowError("Berichtigung einer Zahlungszuordnung benötigt Freigabe und Grund")
    workflow.archive.verify();before=workflow.archive.catalog();after=copy.deepcopy(before)
    if event_id not in after.get("cash_events",{}) or event_id in after.get("cash_event_voids",{}):
        raise WorkflowError("Zahlungszuordnung fehlt oder wurde bereits berichtigt")
    after.setdefault("cash_event_voids",{})[event_id]={"reason":reason,"at":now()}
    after["cash_source_overrides"][after["cash_events"][event_id]["record_id"]]["complete"]=False
    workflow.commit(before,after,{})
    return {"ok":True,"voided":event_id,"bank_refund_executed":False}
