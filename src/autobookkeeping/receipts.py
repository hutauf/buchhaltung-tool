"""Read originals locally, prepare encrypted metadata, book only a reviewed revision."""
from __future__ import annotations
import copy
import json
import re
import shutil
import subprocess
import unicodedata
from datetime import date
from decimal import Decimal
from pathlib import Path

from autobookkeeping.archive import atomic, encoded, outside, sha, within
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError, now
from autobookkeeping.taxes import decimal_money
from autobookkeeping.einvoices import embedded_xml, inspect_xml

CATEGORIES = ("software_subscriptions", "marketplace_fees", "postage", "office", "goods", "other")
TAX_TYPES = ("as_documented", "no_vat_shown", "mixed", "special_review")


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def supplier(row):
    return row.get("payee") or (row.get("source_record") or {}).get("expense", {}).get("payee")


def existing(catalog, digest, metadata=None):
    hard=[]; possible=[]
    for rid,value in catalog["records"].items():
        row=value["current"]
        hashes={catalog["documents"][n]["sha256_plaintext"] for n in row["documents"]}
        if digest in hashes:
            hard.append(rid);continue
        if metadata and row["kind"] in ("expense", "expense_credit") and normalized(supplier(row))==normalized(metadata["payee"]):
            same_number=metadata.get("number") and normalized(row.get("number"))==normalized(metadata["number"])
            same_context=(row.get("date","")[:10]==metadata["date"] and row.get("gross")==metadata["gross"])
            if same_number:
                hard.append(rid)
            elif same_context and rid != metadata.get('original_id'):
                possible.append(rid)
    return {"existing_records":sorted(hard), "possible_duplicates":sorted(possible)}


def dhl_guard(catalog,digest):
    if any(entry["sha256_plaintext"]==digest and entry.get("role")=="unbooked_receipt" for entry in catalog["documents"].values()):
        raise WorkflowError("Vorgemerkten DHL-Beleg über den zugehörigen Rechnungsabschluss buchen")


def structured_source(data, extension):
    try:
        xml = data if extension == '.xml' else embedded_xml(data) if extension == '.pdf' else None
        return (xml, inspect_xml(xml)) if xml is not None else (None, None)
    except ValueError as exc:
        raise WorkflowError(str(exc)) from None


def match_structured(metadata, result):
    if not result: return
    if not result['validation']['en16931_valid']:
        raise WorkflowError('Rechnungs-XML ungültig; Original als Nachweis archivieren und Quelle klären')
    expected = 'credit_note' if metadata.get('document_type') == 'supplier_credit' else 'invoice'
    if result['document_type'] != expected:
        raise WorkflowError('XML-Belegart passt nicht zu Ausgabe/Lieferanten-Korrektur')
    source = result['metadata']
    for field in ('payee', 'number', 'date', 'currency', 'supplier_country', 'vat_rate'):
        if metadata.get(field) != source.get(field):
            raise WorkflowError('Geprüfte Metadaten weichen von Rechnungs-XML ab: ' + field)
    for field in ('gross', 'net', 'vat'):
        if Decimal(metadata[field]) != Decimal(source[field]):
            raise WorkflowError('Geprüfte Beträge weichen von Rechnungs-XML ab: ' + field)
    if metadata.get('vat_breakdown', []) != source.get('vat_breakdown', []):
        raise WorkflowError('Steuergruppen weichen von Rechnungs-XML ab')
    if source['tax_review_required'] and not metadata['tax_review_required']:
        raise WorkflowError('Offene Sondersteuerprüfung der XML darf nicht entfallen')


def validate_metadata(raw):
    if not isinstance(raw,dict):raise WorkflowError("Metadaten müssen ein JSON-Objekt sein")
    result=copy.deepcopy(raw)
    allowed={"payee","number","date","currency","gross","net","vat","vat_rate","vat_breakdown","tax_treatment",
             "tax_review_required","tax_review_note","description","category","pay_date","paid_amount","payment_evidence",
             "service_period_start","service_period_end","supplier_country","business_use","verification_basis","duplicate_review",
             "document_type","original_id","correction_reason"}
    if set(result)-allowed:raise WorkflowError("Unbekannte Metadatenfelder; keine eigenen IDs oder Buchungsstatus setzen")
    for field in ("payee","description","verification_basis"):
        if not isinstance(result.get(field),str) or not result[field].strip():
            raise WorkflowError("Zahlungsempfänger, Beschreibung und konkrete Belegprüfung erforderlich")
        result[field]=result[field].strip()
    for field in ("date","pay_date","service_period_start","service_period_end"):
        value=result.get(field)
        if value is not None:
            if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):raise WorkflowError("Datum als ISO-Kalendertag angeben")
            date.fromisoformat(value)
    if not result.get("date") or result.get("currency")!="EUR":raise WorkflowError("Belegdatum und EUR erforderlich; Fremdwährung separat prüfen")
    if result.get("category") not in CATEGORIES or result.get("tax_treatment") not in TAX_TYPES:
        raise WorkflowError("Ausgabenkategorie und dokumentierte Steuerbehandlung erforderlich")
    if type(result.get("tax_review_required")) is not bool:raise WorkflowError("Offene Steuerprüfung ausdrücklich markieren")
    if result.get("business_use") not in ("business","mixed","unclear"):raise WorkflowError("Betriebliche Nutzung ausdrücklich zuordnen")
    if result.get("number") is not None and (not isinstance(result["number"],str) or not result["number"].strip()):
        raise WorkflowError("Lieferanten-Belegnummer als Text oder null angeben")
    if result.get('document_type', 'expense') not in ('expense', 'supplier_credit'):
        raise WorkflowError('Ausgabe oder Lieferanten-Korrektur auswählen')
    if result.get('document_type') == 'supplier_credit':
        if not all(isinstance(result.get(k),str) and result[k].strip() for k in ('original_id','correction_reason')):
            raise WorkflowError('Lieferanten-Korrektur benötigt Originalausgabe und konkreten Grund')
    elif result.get('original_id') or result.get('correction_reason'):
        raise WorkflowError('Originalbezug nur für Lieferanten-Korrekturen angeben')
    if result.get("supplier_country") is not None and not re.fullmatch(r"[A-Z]{2}",result["supplier_country"]):
        raise WorkflowError("Lieferantenland als ISO-Code oder null angeben")
    if result.get("supplier_country") not in (None,"DE") or result["tax_treatment"]=="special_review":
        if not result["tax_review_required"]:raise WorkflowError("Ausländische/Sondersteuer-Belege erfordern eine markierte Steuerprüfung")
    if result["tax_review_required"] and not str(result.get("tax_review_note") or "").strip():
        raise WorkflowError("Offene steuerliche Zuordnung konkret beschreiben")
    if any(result.get(k) is None for k in ("gross","net","vat")):raise WorkflowError("Dokumentierte Beträge fehlen")
    for field in ("gross","net","vat"):
        value=Decimal(str(result[field]))
        if not value.is_finite() or value!=decimal_money(value):raise WorkflowError("Beträge müssen endliche Centbeträge sein")
        result[field]=str(decimal_money(value))
    gross,net,vat=(Decimal(result[k]) for k in ("gross","net","vat"))
    if gross<=0 or min(net,vat)<0 or gross!=net+vat:raise WorkflowError("Positiver Ausgabenbeleg mit Brutto = Netto + Steuer erforderlich")
    rate=result.get("vat_rate")
    if rate is not None and (type(rate) not in (int,float) or not 0<=rate<=100):raise WorkflowError("Steuersatz muss dokumentiert oder null sein")
    if result["tax_treatment"]=="no_vat_shown" and (vat or rate is not None):
        raise WorkflowError("Ohne ausgewiesene Steuer keine Steuersatzbehauptung; vat_rate null verwenden")
    breakdown=result.get("vat_breakdown") or []
    if result["tax_treatment"]=="mixed" and (rate is not None or not breakdown):raise WorkflowError("Gemischte Steuern nach Gruppen aufschlüsseln")
    if breakdown:
        totals={k:Decimal(0) for k in ("gross","net","vat")}
        for group in breakdown:
            if set(group)!={"gross","net","vat","vat_rate"} or type(group["vat_rate"]) not in (int,float) or not 0<=group["vat_rate"]<=100:
                raise WorkflowError("Steuergruppe benötigt Brutto, Netto, Steuer und Satz")
            values={k:decimal_money(group[k]) for k in totals}
            if any(Decimal(str(group[k]))!=values[k] for k in totals):
                raise WorkflowError("Steuergruppen benötigen exakte Centbeträge")
            if values["gross"]!=values["net"]+values["vat"] or min(values.values())<0:raise WorkflowError("Steuergruppe ist nicht stimmig")
            for k in totals:totals[k]+=values[k];group[k]=str(values[k])
        if any(totals[k]!=Decimal(result[k]) for k in totals):raise WorkflowError("Steuergruppen stimmen nicht mit Gesamtbetrag überein")
    if result.get("service_period_start") and result.get("service_period_end") and result["service_period_start"]>result["service_period_end"]:
        raise WorkflowError("Leistungszeitraum ist umgekehrt")
    if result.get("pay_date"):
        if result.get("paid_amount") is None or not str(result.get("payment_evidence") or "").strip():raise WorkflowError("Zahlungsdatum benötigt Betrag und geprüften Zahlungsnachweis")
        paid=decimal_money(result["paid_amount"])
        if Decimal(str(result["paid_amount"]))!=paid or not 0<paid<=gross:raise WorkflowError("Zahlungsbetrag muss ein Centbetrag innerhalb des Belegbetrags sein")
        result["paid_amount"]=str(paid)
    elif result.get("paid_amount") is not None or result.get("payment_evidence"):
        raise WorkflowError("Zahlungsnachweis benötigt ein konkretes Zahlungsdatum")
    return result


def check_credit(catalog, metadata):
    if metadata.get('document_type') != 'supplier_credit':
        return None
    original = catalog.get('records', {}).get(metadata['original_id'], {}).get('current', {})
    if original.get('kind') != 'expense' or original.get('status') in ('draft','test_draft','cancelled'):
        raise WorkflowError('Lieferanten-Korrektur benötigt eine bereits erfasste Originalausgabe')
    if not supplier(original) or normalized(supplier(original)) != normalized(metadata['payee']):
        raise WorkflowError('Lieferant der Korrektur stimmt nicht mit Originalausgabe überein')
    if original.get('currency','EUR') != metadata['currency'] or metadata['date'] < original['date'][:10]:
        raise WorkflowError('Währung oder Datum der Lieferanten-Korrektur passt nicht zum Original')
    credits = [v['current'] for v in catalog['records'].values()
               if v['current'].get('kind') == 'expense_credit' and v['current'].get('original_id') == original['id']]
    for field in ('gross','net','vat'):
        if original.get(field) is None or sum((-Decimal(c[field]) for c in credits), Decimal(0)) + Decimal(metadata[field]) > Decimal(original[field]):
            raise WorkflowError('Lieferanten-Minderung übersteigt verbleibenden Originalbetrag/Steuer')
    original_rates = {g['vat_rate'] for g in original.get('vat_breakdown', [])}
    if original.get('vat_rate') is not None: original_rates.add(original['vat_rate'])
    credit_rates = {g['vat_rate'] for g in metadata.get('vat_breakdown', [])}
    if metadata.get('vat_rate') is not None: credit_rates.add(metadata['vat_rate'])
    if original_rates and not credit_rates <= original_rates:
        raise WorkflowError('Steuersatz der Lieferanten-Korrektur passt nicht zum Original')
    if original.get('vat_breakdown'):
        if not metadata.get('vat_breakdown'):
            raise WorkflowError('Korrektur einer gruppierten Steuerrechnung benötigt dieselbe Steuergruppenaufteilung')
        for group in metadata.get('vat_breakdown', []):
            for field in ('gross','net','vat'):
                available = sum((Decimal(g[field]) for g in original['vat_breakdown'] if g['vat_rate']==group['vat_rate']),Decimal(0))
                used = sum((-Decimal(g[field]) for c in credits for g in c.get('vat_breakdown',[]) if g['vat_rate']==group['vat_rate']),Decimal(0))
                if used + Decimal(group[field]) > available:
                    raise WorkflowError('Steuergruppen-Minderung übersteigt verbleibende Originalgruppe')
    return original


def check_structured_original(original, structured):
    references = structured.get('original_numbers', []) if structured else []
    if original and references and (len(set(references)) != 1 or normalized(original.get('number')) != normalized(references[0])):
        raise WorkflowError('Originalbezug der Lieferanten-XML passt nicht zur ausgewählten Ausgabe')


class Receipts:
    def __init__(self,workflow:LocalInvoices):
        self.workflow=workflow;self.archive=workflow.archive

    def inspect(self,source:Path,target:Path,original_id=None):
        import pymupdf
        source=source.resolve();target=outside(self.archive.repo,target)
        if target.exists():raise WorkflowError("Prüfordner muss neu sein")
        if source.is_relative_to(self.archive.root) and source.suffix==".enc":
            self.archive.verify();catalog=self.archive.catalog()
            name=source.relative_to(self.archive.root).as_posix()
            if name not in catalog["documents"]:raise WorkflowError("Verschlüsselter Beleg ist nicht inventarisiert")
            data=self.archive.read(name);extension=Path(name[:-4]).suffix.lower()
        else:
            name=None;data=source.read_bytes();extension=source.suffix.lower()
        if extension not in (".pdf",".png",".jpg",".jpeg",".xml"):raise WorkflowError("PDF, XML, PNG oder JPEG erforderlich")
        xml, structured = structured_source(data, extension)
        count=0; pages=[]; texts=[]
        if extension != '.xml':
          with pymupdf.open(stream=data,filetype=extension[1:]) as doc:
            if doc.needs_pass:raise WorkflowError("Passwortgeschütztes PDF separat entsperren")
            count=doc.page_count
            if not count or count>500:raise WorkflowError("Leerer/zu umfangreicher Beleg; gezielte Prüfung erforderlich")
            texts=[page.get_text() for page in doc]
            pages=list(range(count)) if count<=5 else sorted({0,1,2,count-2,count-1})
            atomic(target/("original"+extension),data)
            for index in pages:
                atomic(target/f"seite-{index+1:03d}.png",doc[index].get_pixmap(matrix=pymupdf.Matrix(1.6,1.6)).tobytes("png"))
        else:
            atomic(target/'original.xml',data)
            texts=[encoded(structured).decode('utf-8')]
        if structured:
            atomic(target/'strukturierte-daten.json',encoded(structured))
            if extension != '.xml':atomic(target/'eingebettete-rechnung.xml',xml)
        relocated=False
        if name is None and source.is_relative_to(self.archive.repo):
            relative=source.relative_to(self.archive.repo).as_posix()
            tracked=subprocess.run(["git","-C",str(self.archive.repo),"ls-files","--error-unmatch","--",relative],capture_output=True)
            if tracked.returncode==0:raise WorkflowError("Klartextbeleg ist bereits in Git; historische Bereinigung separat klären")
            if sha(source.read_bytes())!=sha(data):raise WorkflowError("Original wurde während der Prüfung verändert")
            # Preserve the supplied clear original outside; no clear receipt remains inside the repo.
            shutil.move(str(source),str(target/("eingereicht"+extension)));relocated=True
        self.archive.verify();catalog=self.archive.catalog()
        review={"version":1,"source_path":str(source),"source_sha256":sha(data),"extension":extension,
                "archive_document":name,"original_file":"original"+extension,"pages":count,"rendered_pages":[i+1 for i in pages],
                "relocated_outside":relocated,"relocated_source":str(target/("eingereicht"+extension)) if relocated else None,"created_at":now()}
        atomic(target/"review.json",encoded(review))
        atomic(target/"text.txt",("\n\n".join(f"--- Seite {i+1} ---\n"+t for i,t in enumerate(texts))).encode())
        template={"payee":None,"number":None,"date":None,"currency":None,"gross":None,"net":None,"vat":None,
                  "vat_rate":None,"tax_treatment":None,"tax_review_required":False,"description":None,"category":None,
                  "supplier_country":None,"business_use":None,"pay_date":None,"verification_basis":None}
        if structured and structured.get('metadata'):template.update(structured['metadata'])
        if structured and structured.get('document_type') == 'credit_note':
            template.update(document_type='supplier_credit', original_id=None, correction_reason=None)
        if original_id:
            original=catalog.get('records',{}).get(original_id,{}).get('current',{})
            if original.get('kind')!='expense': raise WorkflowError('Lieferanten-Korrektur benötigt vorhandene Originalausgabe')
            template.update(document_type='supplier_credit', original_id=original_id, correction_reason=None)
        atomic(target/"metadaten.json",encoded(template))
        return {"ok":True,"review":str(target/"review.json"),"metadata":str(target/"metadaten.json"),"text":str(target/"text.txt"),
                "pages":count,"images":[str(target/f"seite-{i+1:03d}.png") for i in pages],"source_relocated_outside":relocated,
                "structured_invoice":bool(structured),"xml_validation":structured['validation'] if structured else None,
                "text_characters":sum(len(t) for t in texts),
                "relocated_source":review["relocated_source"],
                **existing(catalog,sha(data))}

    def prepare(self,review_path:Path,metadata_path:Path):
        review_path=outside(self.archive.repo,review_path);review=json.loads(review_path.read_bytes())
        metadata=validate_metadata(json.loads(outside(self.archive.repo,metadata_path).read_bytes()))
        original=outside(self.archive.repo,within(review_path.parent,review["original_file"]));data=original.read_bytes();digest=sha(data)
        if digest!=review["source_sha256"]:raise WorkflowError("Prüfkopie wurde verändert; Original erneut einlesen")
        if review["extension"] not in (".pdf",".png",".jpg",".jpeg",".xml"):raise WorkflowError("Belegformat nicht unterstützt")
        xml, structured = structured_source(data, review['extension'])
        match_structured(metadata, structured)
        self.archive.verify();before=self.archive.catalog();after=copy.deepcopy(before)
        original_row = check_credit(after, metadata)
        check_structured_original(original_row, structured)
        duplicates=existing(after,digest,metadata)
        if duplicates["existing_records"]:raise WorkflowError("Beleg bereits archiviert; vorhandenen Datensatz verwenden")
        if duplicates["possible_duplicates"] and not str(metadata.get("duplicate_review") or "").strip():
            return {"ok":False,"requires_duplicate_review":True,**duplicates}
        dhl_guard(after,digest)
        did="local-expense-draft:"+digest
        previous=after.get("local_expense_drafts",{}).get(did)
        if previous and previous["current"]["status"]=="recorded":raise WorkflowError("Beleg wurde bereits gebucht")
        year=metadata["date"][:4];documents={}
        name=review.get("archive_document")
        if name and (name not in after["documents"] or after["documents"][name]["sha256_plaintext"]!=digest):
            raise WorkflowError("Vorhandener verschlüsselter Originalbeleg passt nicht zur Prüfung")
        if not name or not name.startswith(year+"/Ausgaben/"):
            name=f"{year}/Ausgaben/{digest}{review['extension']}.enc";documents[name]=data
        candidate=dict(metadata,id=did,kind="expense",document_type=metadata.get('document_type','expense'),status="test_draft",source="local",year=year,
                       number=metadata.get("number"),documents=[name],coverage="complete",source_sha256=digest,
                       duplicate_candidates=duplicates["possible_duplicates"],metadata=metadata)
        if original_row:
            candidate.update(original_revision=sha(encoded(original_row)), original_number=original_row.get('number'))
        if structured:
            candidate['structured_invoice'] = structured
            extras=[('validation.json',encoded(structured),'e_invoice_validation')]
            if review['extension'] != '.xml':extras.append(('xml',xml,'e_invoice_xml'))
            for suffix,payload,role in extras:
                extra=f"{year}/Ausgaben/{sha(payload)}.{suffix}.enc"
                candidate['documents'].append(extra)
                if extra not in after['documents']:
                    documents[extra]=payload
                    after['documents'][extra]={'record_id':did,'role':role,'sha256_plaintext':sha(payload),'bytes_plaintext':len(payload)}
        candidate["provenance"] = copy.deepcopy(previous["current"]["provenance"]) if previous else {
            "first_source_path":review["source_path"],"source_sha256":digest,"inspected_at":review["created_at"],
            "relocated_source":review.get("relocated_source")}
        candidate["revision"]=sha(encoded(candidate))
        if previous and previous["current"]==candidate:return self.summary(candidate)
        if name not in after["documents"]:
            after["documents"][name]={"record_id":did,"role":"expense_receipt_candidate","sha256_plaintext":digest,"bytes_plaintext":len(data)}
        after.setdefault("local_expense_drafts",{})[did]={"current":candidate,"history":previous["history"]+[previous["current"]] if previous else []}
        self.workflow.commit(before,after,documents)
        return self.summary(candidate)

    @staticmethod
    def summary(row):
        return {"ok":True,"id":row["id"],"status":row["status"],"revision":row["revision"],"metadata":row["metadata"],
                "documents":row["documents"],"booked":row["status"]=="recorded","record_id":row.get("record_id")}

    def book(self,draft_id,revision,approved):
        if not approved:raise WorkflowError("Ausgabe benötigt Freigabe der konkret geprüften Metadaten und Revision")
        self.archive.verify();before=self.archive.catalog();after=copy.deepcopy(before)
        value=after["local_expense_drafts"][draft_id];candidate=value["current"]
        if candidate["revision"]!=revision:raise WorkflowError("Belegmetadaten geändert; neue Revision prüfen und freigeben")
        if candidate["status"]=="recorded":return {"ok":True,"changed":False,"record_id":candidate["record_id"]}
        if candidate["status"]!="test_draft":raise WorkflowError("Nur aktive Belegvormerkungen buchen")
        if sha(encoded({k:v for k,v in candidate.items() if k!="revision"}))!=revision:
            raise WorkflowError("Metadatenrevision passt nicht zum vorgemerkten Inhalt")
        metadata=validate_metadata(candidate["metadata"]);digest=candidate["source_sha256"]
        original_name=candidate['documents'][0]
        _, structured = structured_source(self.archive.read(original_name),Path(original_name[:-4]).suffix.lower())
        match_structured(metadata, structured)
        original_row = check_credit(after, metadata)
        check_structured_original(original_row, structured)
        if original_row and sha(encoded(original_row)) != candidate['original_revision']:
            raise WorkflowError('Originalausgabe geändert; Lieferanten-Korrektur erneut prüfen')
        dhl_guard(after,digest)
        if existing(after,digest,metadata)["existing_records"]:raise WorkflowError("Zwischenzeitlich als Ausgabe/anderer Beleg archiviert")
        possible=existing(after,digest,metadata)["possible_duplicates"]
        if possible!=candidate["duplicate_candidates"]:raise WorkflowError("Dublettenlage verändert; Vormerkung erneut prüfen")
        rid="local:expense:"+digest
        row=dict(metadata,id=rid,source="local",source_id=digest,kind="expense",status="recorded",year=metadata["date"][:4],
                 number=metadata.get("number"),documents=candidate["documents"],coverage="complete",vat_basis="reviewed_original_receipt",
                 source_record=metadata,recorded_at=now(),approved_revision=revision)
        row["provenance"] = copy.deepcopy(candidate["provenance"])
        if original_row:
            row.update(kind='expense_credit', document_type='supplier_credit', original_id=metadata['original_id'],
                       original_number=original_row.get('number'), original_revision=candidate['original_revision'])
            for field in ('gross','net','vat'): row[field]=str(-Decimal(row[field]))
            if row.get('vat_breakdown'):
                row['vat_breakdown'] = copy.deepcopy(row['vat_breakdown'])
                for group in row['vat_breakdown']:
                    for field in ('gross','net','vat'): group[field]=str(-Decimal(group[field]))
        if candidate.get('structured_invoice'):
            row['structured_invoice'] = copy.deepcopy(candidate['structured_invoice'])
        after["records"][rid]={"current":row,"history":[]}
        value["history"].append(copy.deepcopy(candidate));value["current"]=dict(candidate,status="recorded",record_id=rid,booked_at=now())
        after.setdefault("local_events",[]).append({"action":"supplier_credit" if original_row else "expense_receipt","record_id":rid,"approved_revision":revision,"at":now()})
        self.workflow.commit(before,after,{})
        return {"ok":True,"changed":True,"record_id":rid,"gross":row["gross"],"pay_date":row.get("pay_date")}

    def discard(self,draft_id):
        self.archive.verify();before=self.archive.catalog();after=copy.deepcopy(before);value=after["local_expense_drafts"][draft_id]
        if value["current"]["status"]!="test_draft":raise WorkflowError("Nur ungebookte Belegvormerkungen verwerfen")
        value["history"].append(copy.deepcopy(value["current"]));value["current"].update(status="discarded",discarded_at=now())
        self.workflow.commit(before,after,{})
        return {"ok":True,"discarded":draft_id,"original_preserved":True}
