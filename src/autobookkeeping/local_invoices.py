"""Local invoice lifecycle. Drafts are separate from actual accounting records.

The CLI serializes all archive access. No service writes or customer communication.
Supported: paid domestic EUR sales, exemption or explicitly assigned 7/19 % VAT.
"""
from __future__ import annotations

import base64
import copy
import io
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from autobookkeeping.archive import Archive, atomic, encoded, outside, seal, sha, unseal
from autobookkeeping.models import EbayOrder
from autobookkeeping.taxes import calculate


class WorkflowError(ValueError):
    """Safe error messages contain no credentials or buyer data."""


def prevent_invoiz_invoice_write(repo: Path | None = None) -> None:
    """After the approved handover, the checked-in invoiz helpers stop issuing."""
    from autobookkeeping.workspace import data_root
    repo = repo or data_root()
    archive = Archive(repo)
    if (archive.root / "database.json.enc").exists():
        if (repo / "output/local-invoice-transaction.enc").exists():
            raise WorkflowError("Unterbrochene lokale Transaktion zuerst prüfen")
        if archive.catalog().get("local_invoice_settings", {}).get("mode") == "local":
            raise WorkflowError("Nummernvergabe ist lokal übernommen; Invoiz-Rechnungsschreibvorgänge sind gesperrt")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today() -> str:
    return datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()


def day(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()


def amount(value) -> str:
    value = Decimal(str(value))
    if not value.is_finite() or value < 0:
        raise WorkflowError("Beträge müssen endlich und nicht negativ sein")
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def euro(value) -> str:
    return f"{Decimal(value):.2f}".replace(".", ",") + " €"


def order_snapshot(order: EbayOrder) -> dict:
    if not order.paid_at or not order.items:
        raise WorkflowError("Nur bezahlte Bestellungen mit Positionen vorbereiten")
    address = order.shipping_address
    if order.currency != "EUR" or address.country_iso != "DE":
        raise WorkflowError("Aktuell nur inländische EUR-Verkäufe unterstützt")
    if not all((address.name.strip(), address.street.strip(), address.postal_code.strip(), address.city.strip())):
        raise WorkflowError("Vollständige Käuferanschrift fehlt")
    positions = []
    for item in order.items:
        if not item.title.strip() or item.quantity <= 0 or item.currency != "EUR":
            raise WorkflowError("Position, Menge oder Währung ungültig")
        unit_price = amount(item.price)
        positions.append({"title": item.title, "quantity": item.quantity, "unit": "Stk.",
                          "unit_gross": unit_price, "gross": amount(Decimal(unit_price) * item.quantity),
                          "vat_rate": 0, "item_id": item.item_id, "transaction_id": item.transaction_id})
    if Decimal(amount(order.shipping_cost)):
        positions.append({"title": "Versandkosten", "description": order.shipping_service,
                          "quantity": 1, "unit": "Stk.", "unit_gross": amount(order.shipping_cost),
                          "gross": amount(order.shipping_cost), "vat_rate": 0})
    gross = amount(sum((Decimal(p["gross"]) for p in positions), Decimal(0)))
    if gross != amount(order.total_value):
        raise WorkflowError("Positionssumme stimmt nicht mit der eBay-Zahlung überein")
    return {"order_id": order.order_id, "sales_record_number": order.sales_record_number,
            "order_id_aliases": list(order.order_id_aliases), "order_status": order.order_status,
            "paid_at": order.paid_at.isoformat(), "delivery_date": day(order.shipped_at),
            "tracking_number": order.tracking_number,
            "buyer": {"name": address.name, "street": address.street, "postal_code": address.postal_code,
                      "city": address.city, "country": address.country or "Deutschland", "country_iso": "DE"},
            "positions": positions, "currency": "EUR", "gross": gross, "net": gross, "vat": "0.00"}


def same_order(left: dict, right: dict) -> bool:
    if left.get("sales_record_number") and right.get("sales_record_number"):
        if str(left["sales_record_number"]) == str(right["sales_record_number"]):
            return True
    identifiers = lambda r: {str(x) for x in [r.get("order_id"), *r.get("order_id_aliases", [])] if x}
    if identifiers(left) & identifiers(right):
        return True
    transactions = lambda r: {(str(p["item_id"]), str(p["transaction_id"])) for p in r.get("positions", [])
                              if p.get("item_id") and p.get("transaction_id")}
    return bool(transactions(left) & transactions(right))


def record_context(row: dict) -> dict:
    if row.get("order_id"):
        return row
    source = row.get("source_detail") or row.get("source_record") or {}
    customer = source.get("customerData") or {}
    return {"order_id": customer.get("number"), "positions": source.get("positions", [])}


def number_state(catalog: dict) -> tuple[int, int]:
    numbers = []
    for value in catalog["records"].values():
        for row in [value["current"], *value["history"]]:
            if row["kind"] not in ("invoice", "credit_note") or not row.get("number"):
                continue
            text = str(row["number"])
            if not re.fullmatch(r"\d+", text):
                raise WorkflowError("Nummernformat erfordert eine explizite Migration")
            numbers.append(text)
    baseline = str(catalog.get("local_invoice_settings", {}).get("last_service_number", "0"))
    numbers.append(baseline)
    largest = max(numbers, key=int)
    return int(largest), max(4, len(largest))


def render_pdf(invoice: dict, draft: bool) -> bytes:
    # Bundled Vera fonts embed German Unicode without an OS font dependency.
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    fonts = Path(reportlab.__file__).parent / "fonts"
    for name, filename in (("Invoice", "Vera.ttf"), ("InvoiceBold", "VeraBd.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    normal = ParagraphStyle("normal", fontName="Invoice", fontSize=9, leading=14, textColor=colors.HexColor("#253347"))
    bold = ParagraphStyle("bold", parent=normal, fontName="InvoiceBold")
    small = ParagraphStyle("small", parent=normal, fontSize=8, leading=12)
    heading = ParagraphStyle("heading", parent=bold, fontSize=25, leading=30)
    right = ParagraphStyle("right", parent=normal, alignment=TA_RIGHT)
    def p(text, style=normal):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)
    seller, buyer = invoice["seller"], invoice["buyer"]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=19*mm, bottomMargin=37*mm, title="Testentwurf" if draft else f"Rechnung {invoice['number']}",
                            author=seller["name"])
    story = [p(seller["name"], bold), p(f"{seller['street']} · {seller['postal_code']} {seller['city']}", small), Spacer(1, 11*mm)]
    document_type = invoice.get("document_type", "invoice")
    document_label = {"invoice": "Rechnung", "cancellation": "Stornorechnung", "partial_refund": "Teilerstattung",
                      "correction": "Rechnungsberichtigung"}[document_type]
    if draft:
        story.extend([p("TESTENTWURF", heading), p(document_label + ": noch nicht ausgestellt. Keine Belegnummer vergeben.", bold)])
    else:
        story.append(p(f"{document_label} {invoice.get('document_number') or invoice['number']}", heading))
    if invoice.get("original_number"):
        story.append(p(f"Bezug: Rechnung {invoice['original_number']} vom {invoice['original_date']}", bold))
    story.extend([Spacer(1, 10*mm), p(buyer["name"], bold), p(buyer["street"]),
                  p(f"{buyer['postal_code']} {buyer['city']}"), p(buyer["country"]), Spacer(1, 9*mm)])
    facts = [[p("Belegnummer", small), p("noch nicht vergeben" if draft else invoice.get("document_number") or invoice["number"], bold)],
             [p("Entwurfsdatum" if draft else "Rechnungsdatum", small), p(datetime.fromisoformat(invoice["date"]).strftime("%d.%m.%Y"))],
             [p("Lieferdatum", small), p(datetime.fromisoformat(invoice["delivery_date"]).strftime("%d.%m.%Y") if invoice.get("delivery_date") else "noch zu prüfen")],
             [p("eBay-Bestellung", small), p(invoice["order_id"])]]
    facts_table = Table(facts, colWidths=[43*mm, 127*mm])
    facts_table.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING",(0,0),(-1,-1),0), ("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    story.extend([facts_table, Spacer(1, 7*mm), p(seller["introduction"]), Spacer(1, 5*mm)])
    if document_type == "correction":
        story.append(p("Folgende Angaben der Originalrechnung werden berichtigt:", bold))
        for change in invoice["correction_changes"]:
            story.extend([Spacer(1, 3*mm), p(change["label"], bold), p("Bisher: " + str(change["before"])),
                          p("Berichtigt: " + str(change["after"]))])
        story.extend([Spacer(1, 5*mm), p("Betrag und Steuerbeträge bleiben unverändert. Dieses Dokument zusammen mit der Originalrechnung aufbewahren.")])
    rows = [[p("Bezeichnung", bold), p("Menge", bold), p("Einzelpreis", bold), p("Gesamt", bold)]]
    for position in invoice["positions"] if document_type != "correction" else []:
        description = position["title"] + ("\n" + position["description"] if position.get("description") else "")
        if not invoice.get("small_business", True):
            description += f"\nUmsatzsteuer {position['vat_rate']} %"
        rows.append([p(description), p(f"{position['quantity']} {position['unit']}"), p(euro(position["unit_gross"]), right), p(euro(position["gross"]), right)])
    table = Table(rows, colWidths=[88*mm, 24*mm, 29*mm, 29*mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eaf0f5")),
                              ("VALIGN",(0,0),(-1,-1),"TOP"), ("TOPPADDING",(0,0),(-1,-1),10),
                              ("BOTTOMPADDING",(0,0),(-1,-1),10), ("LINEBELOW",(0,0),(-1,-1),0.4,colors.HexColor("#dce3ec"))]))
    total = Table([[p("Gesamtbetrag", bold), p(euro(invoice["gross"]), bold)]], colWidths=[141*mm, 29*mm])
    total.setStyle(TableStyle([("ALIGN",(-1,0),(-1,-1),"RIGHT"),("TOPPADDING",(0,0),(-1,-1),12)]))
    if document_type != "correction":
        story.extend([table, total, Spacer(1, 7*mm)])
        if invoice.get("small_business", True):
            story.append(p(seller["tax_note"]))
        else:
            for group in invoice["vat_breakdown"]:
                story.append(p(f"Netto {euro(group['net'])} + {group['vat_rate']} % USt {euro(group['vat'])} = {euro(group['gross'])}"))
        story.extend([Spacer(1, 3*mm), p("Bereits über eBay bezahlt." if document_type == "invoice" else
                                            "Dieses Dokument löst keine Auszahlung aus. Die Rückzahlung wird separat erfasst.")])
    if invoice.get("reason"):
        story.extend([Spacer(1, 3*mm), p("Grund: " + invoice["reason"])])
    if draft:
        story.extend([Spacer(1, 6*mm), p("Nur zur Prüfung: Dieser Testentwurf verbraucht und reserviert keine Nummer. Ausstellung und Versand sind noch nicht erfolgt.", small)])
    def page(canvas, document):
        canvas.saveState()
        if draft:
            canvas.setFillColor(colors.HexColor("#ba6c10"))
            canvas.setFont("InvoiceBold", 8)
            canvas.drawString(20*mm, 285*mm, "TESTENTWURF · KEINE AUSGESTELLTE RECHNUNG")
        canvas.setStrokeColor(colors.HexColor("#dce3ec")); canvas.line(20*mm,30*mm,190*mm,30*mm)
        footer = f"{seller['name']}\n{seller['street']} · {seller['postal_code']} {seller['city']}\nSteuernummer: {seller['tax_number']}"
        if seller.get("email"):
            footer += " · " + seller["email"]
        para = p(footer, small); _, height = para.wrap(155*mm, 24*mm)
        para.drawOn(canvas,20*mm,27*mm-height)
        canvas.setFont("Invoice",8); canvas.drawRightString(190*mm,12*mm,f"Seite {document.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=page, onLaterPages=page)
    return buffer.getvalue()


class LocalInvoices:
    def __init__(self, archive: Archive):
        self.archive = archive
        self.journal = archive.repo / "output/local-invoice-transaction.enc"

    def recover(self) -> bool:
        """Finish an already authorized encrypted transaction after interruption."""
        if not self.journal.exists():
            return False
        transaction = json.loads(unseal(self.archive.unlock(), self.journal.read_bytes(), "local-invoice-transaction"))
        current = sha(encoded(self.archive.catalog()))
        if current not in (transaction["before_sha256"], sha(encoded(transaction["after"]))):
            raise WorkflowError("Offene Transaktion kollidiert mit einem anderen Datenbankstand")
        for name, payload in transaction["documents"].items():
            data = base64.b64decode(payload, validate=True)
            if (self.archive.root / name).exists() and self.archive.read(name) != data:
                raise WorkflowError("Transaktion würde ein vorhandenes Original überschreiben")
            self.archive.write(name, data)
        self.archive.save_catalog(transaction["after"])
        self.archive.verify()
        self.journal.unlink()
        return True

    def commit(self, before: dict, after: dict, documents: dict[str, bytes]) -> None:
        if self.journal.exists():
            raise WorkflowError("Offene Transaktion zuerst mit recover abschließen")
        if sha(encoded(self.archive.catalog())) != sha(encoded(before)):
            raise WorkflowError("Datenbank wurde gleichzeitig geändert")
        transaction = {"before_sha256": sha(encoded(before)), "after": after,
                       "documents": {name: base64.b64encode(data).decode() for name, data in documents.items()}}
        atomic(self.journal, seal(self.archive.unlock(), encoded(transaction), "local-invoice-transaction"))
        self.recover()

    def configure(self, seller: dict, last_service_number: str, reference: dict) -> None:
        self.archive.verify()
        before = self.archive.catalog(); after = copy.deepcopy(before)
        if after.get("local_invoice_settings"):
            raise WorkflowError("Profil bereits vorhanden; Änderungen benötigen einen eigenen Migrationsschritt")
        required = ("name", "street", "postal_code", "city", "tax_number", "tax_note", "introduction")
        if not all(isinstance(seller.get(k), str) and seller[k].strip() for k in required):
            raise WorkflowError("Absenderprofil unvollständig")
        if seller.get("country_iso") != "DE" or seller.get("small_business") is not True or "19" not in seller["tax_note"]:
            raise WorkflowError("Aktuell nur deutsche Kleinunternehmer-Rechnungen unterstützt")
        if not re.fullmatch(r"\d{4,}", last_service_number):
            raise WorkflowError("Fortlaufende numerische Service-Rechnungsnummer erforderlich")
        last, _ = number_state(before)
        if int(last_service_number) != last:
            raise WorkflowError("Service-Nummernstand weicht vom Archiv ab; Backup aktualisieren")
        after["local_invoice_settings"] = {"seller": copy.deepcopy(seller), "last_service_number": last_service_number,
                                             "mode": "trial", "reference": reference, "configured_at": now()}
        after["local_invoice_drafts"] = {}
        after["local_workflow"] = {}
        self.commit(before, after, {})

    def check_duplicates(self, catalog: dict, context: dict, replacement_of: str | None = None) -> None:
        from autobookkeeping.adjustments import fully_cancelled
        if replacement_of:
            previous = catalog["records"].get(replacement_of, {}).get("current", {})
            if previous.get("source") != "local" or not same_order(previous, context) or not fully_cancelled(catalog, replacement_of):
                raise WorkflowError("Ersatzrechnung benötigt eine vollständig stornierte lokale Originalrechnung desselben Verkaufs")
        checklist_path = self.archive.repo / "bookkeeping_checklist.json.enc"
        checklists = [catalog.get("workflow_checklist", {})]
        if checklist_path.exists():
            checklists.append(__import__("autobookkeeping.checklist", fromlist=["ChecklistStore"]).ChecklistStore(checklist_path).load())
        elif (self.archive.repo / 'bookkeeping_checklist.json').exists():
            # Compatibility for old local imports; new workspaces store only .enc.
            checklists.append(json.loads((self.archive.repo / 'bookkeeping_checklist.json').read_bytes()))
        for checklist in checklists:
            items = checklist.get("items", [])
            if isinstance(items, dict):
                items = items.values()
            for item in items:
                if same_order(item, context) and (item.get("invoice_id") or item.get("invoice_number") or item.get("expense_id")):
                    raise WorkflowError("Bestellung besitzt bereits Buchhaltungsdaten in der Checkliste")
        for rid, value in catalog["records"].items():
            if value["current"]["kind"] == "invoice" and same_order(record_context(value["current"]), context):
                if replacement_of and fully_cancelled(catalog, rid):
                    continue
                raise WorkflowError("Bestellung besitzt bereits eine Rechnung im Archiv")

    def prepare(self, order: EbayOrder, checks: dict, attachment: tuple[dict, bytes] | None = None,
                rates: list[int] | None = None, replacement_of: str | None = None) -> dict:
        self.archive.verify()
        before = self.archive.catalog(); after = copy.deepcopy(before)
        config = after.get("local_invoice_settings")
        if not config:
            raise WorkflowError("Absenderprofil zuerst einrichten")
        if config["mode"] == "trial" and not checks.get("invoiz_checked"):
            raise WorkflowError("Im Probebetrieb ist die Invoiz-Dublettenprüfung erforderlich")
        if not checks.get("vine_checked") or not checks.get("dhl_checked"):
            raise WorkflowError("DHL- und Vine-Leseprüfungen vor dem Entwurf erforderlich")
        if checks.get("invoice_matches") or checks.get("expense_matches"):
            raise WorkflowError("Invoiz enthält bereits Rechnung oder Ausgabe für diese Bestellung")
        snapshot = order_snapshot(order)
        self.check_duplicates(after, snapshot, replacement_of)
        tax = calculate(snapshot["positions"], config["seller"]["small_business"], rates)
        existing = [d for d in after["local_invoice_drafts"].values()
                    if d["current"]["status"] == "test_draft" and same_order(d["current"], snapshot)]
        if len(existing) > 1:
            raise WorkflowError("Mehrere aktive lokale Entwürfe für denselben Verkauf")
        invoice_id = existing[0]["current"]["id"] if existing else "local-draft:" + uuid.uuid4().hex
        invoice = dict(snapshot, id=invoice_id, status="test_draft", number=None, date=today(),
                       year=today()[:4], seller=copy.deepcopy(config["seller"]),
                       **tax,
                       checks=checks, created_at=existing[0]["current"]["created_at"] if existing else now())
        if replacement_of:
            invoice["replacement_of"] = replacement_of
        # Compare business content, not the timestamp of a repeated source check.
        if existing:
            current = existing[0]["current"]
            attachment_same = attachment is None or (
                current.get("receipt_candidate") and
                all(current["receipt_candidate"].get(k) == v for k, v in attachment[0].items()) and
                after["documents"][current["receipt_candidate"]["document"]]["sha256_plaintext"] == sha(attachment[1]))
            if attachment_same and all(current.get(k) == v for k, v in invoice.items() if k != "checks"):
                return self.summary(current, after)
        pdf = render_pdf(invoice, draft=True)
        name = f"{invoice['year']}/Rechnungen/{sha((invoice_id + ':' + sha(pdf)).encode())}.pdf.enc"
        invoice["documents"] = [name]
        documents = {name: pdf}
        after["documents"][name] = {"record_id": invoice_id, "role": "test_draft",
                                     "sha256_plaintext": sha(pdf), "bytes_plaintext": len(pdf)}
        if attachment:
            receipt, data = attachment
            if not data.startswith(b"%PDF-"):
                raise WorkflowError("DHL-Original ist kein PDF")
            receipt_name = f"{invoice['year']}/Ausgaben/{sha((invoice_id + ':receipt:' + sha(data)).encode())}.pdf.enc"
            documents[receipt_name] = data
            after["documents"][receipt_name] = {"record_id": invoice_id, "role": "unbooked_receipt",
                                               "sha256_plaintext": sha(data), "bytes_plaintext": len(data)}
            invoice["receipt_candidate"] = dict(receipt, document=receipt_name, booked=False)
        elif existing and existing[0]["current"].get("receipt_candidate"):
            invoice["receipt_candidate"] = existing[0]["current"]["receipt_candidate"]
        invoice["revision"] = sha(encoded(invoice))
        history = existing[0]["history"] + [existing[0]["current"]] if existing else []
        after["local_invoice_drafts"][invoice_id] = {"current": invoice, "history": history}
        self.commit(before, after, documents)
        return self.summary(invoice, after)

    @staticmethod
    def summary(invoice: dict, catalog: dict) -> dict:
        last, width = number_state(catalog)
        result = {"id": invoice["id"], "status": invoice["status"], "number": invoice["number"],
                "proposed_number": str(last + 1).zfill(width) if invoice["status"] == "test_draft" else None,
                "revision": invoice["revision"], "gross": invoice["gross"], "currency": "EUR",
                "number_reserved": invoice["status"] == "issued", "documents": invoice["documents"]}
        if invoice.get("receipt_candidate"):
            result["receipt_candidate_sha256"] = sha(encoded(invoice["receipt_candidate"]))
            result["receipt_gross"] = invoice["receipt_candidate"]["gross"]
        return result

    def activate(self, last_service_number: str, confirmed_live_number: str, approved: bool) -> dict:
        if not approved:
            raise WorkflowError("Produktivwechsel benötigt ausdrückliche Freigabe")
        self.archive.verify()
        before = self.archive.catalog(); after = copy.deepcopy(before)
        settings = after["local_invoice_settings"]
        if settings["mode"] != "trial":
            raise WorkflowError("Produktivwechsel wurde bereits durchgeführt")
        last, _ = number_state(after)
        if int(last_service_number) != last or last_service_number != confirmed_live_number:
            raise WorkflowError("Nummernstand stimmt nicht; vollständigen Service-Bestand zuerst sichern")
        settings.update(mode="local", last_service_number=last_service_number, activated_at=now())
        after["local_events"] = after.get("local_events", []) + [{"action": "handover", "at": now(), "last_service_number": last_service_number}]
        self.commit(before, after, {})
        return {"ok": True, "mode": "local", "last_service_number": last_service_number}

    def issue(self, invoice_id: str, expected_revision: str, expected_number: str, order: EbayOrder, approved: bool) -> dict:
        if not approved:
            raise WorkflowError("Ausstellung benötigt ausdrückliche Freigabe")
        self.archive.verify()
        before = self.archive.catalog(); after = copy.deepcopy(before)
        if after["local_invoice_settings"]["mode"] != "local":
            raise WorkflowError("Probebetrieb: Produktivwechsel wurde noch nicht freigegeben")
        value = after["local_invoice_drafts"][invoice_id]; current = value["current"]
        if current["status"] != "test_draft" or current["revision"] != expected_revision:
            raise WorkflowError("Entwurf wurde geändert, verworfen oder bereits ausgestellt")
        source = order_snapshot(order)
        tax = calculate(source["positions"], current["small_business"], [p["vat_rate"] for p in current["positions"]])
        source.update(tax)
        if current["seller"] != after["local_invoice_settings"]["seller"]:
            raise WorkflowError("Absender/Steuerprofil geändert; Entwurf erneut vorbereiten und prüfen")
        if any(current.get(k) != v for k, v in source.items()):
            raise WorkflowError("eBay-Bestellung hat sich seit der Entwurfsprüfung geändert")
        self.check_duplicates(after, current, current.get("replacement_of"))
        last, width = number_state(after); number = str(last + 1).zfill(width)
        if number != expected_number:
            raise WorkflowError("Nächste Rechnungsnummer hat sich geändert; neu prüfen")
        if not current.get("delivery_date"):
            raise WorkflowError("Lieferdatum vor Ausstellung bestätigen")
        invoice = copy.deepcopy(current)
        invoice.update(id="local:invoice:" + invoice_id.split(":")[-1], number=number, status="issued",
                       date=today(), year=today()[:4], issued_at=now(), source="local", kind="invoice",
                       source_id=invoice_id.split(":")[-1], coverage="complete", vat_basis=current["tax_treatment"],
                       payment_status="paid", pay_date=day(order.paid_at), outstanding="0.00", draft_id=invoice_id)
        invoice.pop("revision")
        pdf = render_pdf(invoice, draft=False)
        name = f"{invoice['year']}/Rechnungen/{sha((invoice['id'] + ':' + sha(pdf)).encode())}.pdf.enc"
        invoice["documents"] = [name]; invoice["revision"] = sha(encoded(invoice))
        after["documents"][name] = {"record_id": invoice["id"], "role": "issued_invoice",
                                    "sha256_plaintext": sha(pdf), "bytes_plaintext": len(pdf)}
        after["records"][invoice["id"]] = {"current": invoice, "history": []}
        value["history"].append(current)
        value["current"] = dict(current, status="issued", number=number, invoice_id=invoice["id"], documents=[name])
        after["local_workflow"][invoice["id"]] = {"order_id": invoice["order_id"], "sales_record_number": invoice["sales_record_number"],
                                                   "status": "rechnung_abgeschlossen", "invoice_number": number, "expense_id": None}
        self.commit(before, after, {name: pdf})
        return self.summary(invoice, after)

    def discard(self, invoice_id: str) -> dict:
        self.archive.verify()
        before = self.archive.catalog(); after = copy.deepcopy(before)
        section = "local_adjustment_drafts" if invoice_id in after.get("local_adjustment_drafts", {}) else "local_invoice_drafts"
        value = after[section][invoice_id]
        if value["current"]["status"] != "test_draft":
            raise WorkflowError("Nur aktive Testentwürfe dürfen verworfen werden")
        value["history"].append(copy.deepcopy(value["current"]))
        value["current"].update(status="discarded", discarded_at=now())
        self.commit(before, after, {})
        return {"ok": True, "status": "discarded", "number_consumed": False}

    def preview(self, invoice_id: str, target: Path) -> dict:
        self.archive.verify()
        target = outside(self.archive.repo, target)
        if target.exists():
            raise WorkflowError("Vorschauziel muss neu sein")
        catalog = self.archive.catalog()
        drafts = {**catalog.get("local_invoice_drafts", {}), **catalog.get("local_adjustment_drafts", {})}
        invoice = (catalog["records"][invoice_id] if invoice_id in catalog["records"] else drafts[invoice_id])["current"]
        if invoice.get("invoice_id"):
            invoice = catalog["records"][invoice["invoice_id"]]["current"]
        if invoice["status"] == "discarded":
            raise WorkflowError("Verworfenen Entwurf nicht als aktuelle Vorschau exportieren")
        atomic(target / "rechnung.pdf", self.archive.read(invoice["documents"][0]))
        atomic(target / "metadaten.json", encoded(invoice))
        return dict(self.summary(invoice, catalog), output=str(target))

    def expense(self, invoice_id: str, candidate_sha256: str, approved: bool) -> dict:
        if not approved:
            raise WorkflowError("Ausgabe benötigt ausdrückliche Freigabe des konkreten Belegs")
        self.archive.verify()
        before = self.archive.catalog(); after = copy.deepcopy(before)
        invoice = after["records"][invoice_id]["current"]
        if invoice["kind"] != "invoice" or invoice["source"] != "local" or invoice["status"] != "issued":
            raise WorkflowError("Ausgabe erst nach lokaler Rechnungsausstellung buchen")
        draft = after["local_invoice_drafts"][invoice["draft_id"]]["current"]
        receipt = draft.get("receipt_candidate")
        if not receipt or sha(encoded(receipt)) != candidate_sha256:
            raise WorkflowError("Belegkandidat fehlt oder entspricht nicht der Freigabe")
        if receipt.get("verified") is not True or receipt.get("vat_rate") != 0:
            raise WorkflowError("DHL-Betrag, Datum, Zuordnung und 0-%-Steuer müssen geprüft sein")
        if receipt.get("order_id") != invoice["order_id"] or not receipt.get("verification_basis"):
            raise WorkflowError("Geprüfter Beleg muss genau dieser Bestellung zugeordnet sein")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(receipt.get("date", ""))):
            raise WorkflowError("Belegdatum muss als ISO-Datum vorliegen")
        datetime.fromisoformat(receipt["date"])
        if receipt.get("pay_date"):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", receipt["pay_date"]):
                raise WorkflowError("Geprüftes Zahlungsdatum muss als ISO-Kalendertag vorliegen")
            datetime.fromisoformat(receipt["pay_date"])
        if not all(isinstance(receipt.get(k), str) and receipt[k].strip() for k in ("payee", "product", "cart_id")):
            raise WorkflowError("Beleglieferant, Produkt oder Warenkorb-ID fehlt")
        state = after["local_workflow"][invoice_id]
        if state.get("expense_id"):
            raise WorkflowError("Passende Ausgabe wurde bereits gebucht")
        receipt_hash = after["documents"][receipt["document"]]["sha256_plaintext"]
        for value in after["records"].values():
            other = value["current"]
            if other["kind"] == "expense" and any(after["documents"][name]["sha256_plaintext"] == receipt_hash for name in other["documents"]):
                raise WorkflowError("Dieser Originalbeleg ist bereits als Ausgabe gebucht")
        rid = "local:expense:" + uuid.uuid4().hex
        description = f"{receipt['product']} - eBay Bestellung {invoice['order_id']} - Rechnung {invoice['number']}"
        if invoice.get("tracking_number"):
            description += " - Sendungsnummer " + invoice["tracking_number"]
        description += " - DHL Warenkorb " + receipt["cart_id"]
        row = {"id": rid, "source": "local", "source_id": rid.split(":")[-1], "kind": "expense",
               "date": receipt["date"], "year": receipt["date"][:4], "status": "recorded", "number": receipt.get("number"),
               "currency": "EUR", "gross": amount(receipt["gross"]), "net": amount(receipt["gross"]), "vat": "0.00", "vat_rate": 0,
               "vat_basis": "verified_original_receipt", "payee": receipt["payee"], "description": description,
               "invoice_id": invoice_id, "invoice_number": invoice["number"], "order_id": invoice["order_id"],
               "sales_record_number": invoice["sales_record_number"], "documents": [receipt["document"]],
               "coverage": "complete", "recorded_at": now(), "source_record": receipt}
        if receipt.get("pay_date"):
            row["pay_date"] = receipt["pay_date"]
        after["records"][rid] = {"current": row, "history": []}
        state.update(status="ok", expense_id=rid)
        draft["receipt_candidate"] = dict(receipt, booked=True, expense_id=rid)
        self.commit(before, after, {})
        return {"ok": True, "expense_id": rid, "gross": row["gross"], "invoice_number": invoice["number"]}
