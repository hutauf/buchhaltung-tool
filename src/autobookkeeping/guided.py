"""Terminal forms: reviewed data stays outside Git until the encrypted draft."""
from __future__ import annotations
from datetime import date
from decimal import Decimal, InvalidOperation
from autobookkeeping.local_invoices import WorkflowError


def ask(label, default=None, optional=False):
    while True:
        value = input(label + (f" [{default}]" if default is not None else "") + ": ").strip()
        if not value and default is not None: value = str(default)
        if value or optional: return value or None
        print("Bitte einen Wert eingeben; Strg+C bricht ab.")


def yes(label, default=False):
    while True:
        value = ask(label + " (ja/nein)", "ja" if default else "nein").casefold()
        if value in ('ja','j','yes','y'): return True
        if value in ('nein','n','no'): return False
        print("Bitte ja oder nein eingeben.")


def money(label, default=None, positive=False):
    while True:
        raw = ask(label + " (EUR)", default)
        try:
            value = Decimal(raw.replace(',', '.'))
            if not value.is_finite() or value != value.quantize(Decimal('.01')) or positive and value <= 0: raise ValueError()
            return f"{value:.2f}"
        except (InvalidOperation, ValueError): print("Bitte einen Centbetrag eingeben, etwa 12,50.")


def day(label, default=None, optional=False):
    while True:
        raw = ask(label + " (JJJJ-MM-TT)", default, optional)
        if raw is None: return None
        try:
            if len(raw) != 10: raise ValueError()
            return date.fromisoformat(raw).isoformat()
        except ValueError: print("Bitte ein gültiges Datum wie 2026-01-31 eingeben.")


def choice(label, values, default=None):
    while True:
        raw=ask(label + " (" + ' / '.join(values) + ")", default)
        if raw in values: return raw
        print("Bitte eine der angezeigten Möglichkeiten wählen.")


def confirm(payload, booking=False):
    import json
    print("\nBitte diese Angaben prüfen (personenbezogene Angaben nur lokal):")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    token = 'BUCHEN' if booking else 'ENTWURF'
    if ask(f"Zum {'Buchen' if booking else 'Vormerken ohne Abschluss'} {token} eingeben") != token:
        raise WorkflowError("Abgebrochen; keine neue Buchung freigegeben")
    return payload


def receipt(template):
    from autobookkeeping.receipts import CATEGORIES, TAX_TYPES, validate_metadata
    p=dict(template)
    for key,label in [('payee','Lieferant'),('number','Belegnummer (leer falls nicht vorhanden)'),('description','Beschreibung')]:
        p[key]=ask(label,p.get(key),optional=key=='number')
    p['date']=day('Belegdatum',p.get('date'));p['currency']='EUR'
    for key,label in [('gross','Brutto'),('net','Netto'),('vat','Ausgewiesene Steuer')]: p[key]=money(label,p.get(key))
    p['tax_treatment']=choice('Steuerangaben laut Beleg',TAX_TYPES,p.get('tax_treatment') or 'no_vat_shown')
    if p['tax_treatment']=='mixed':
        groups=[]
        while True:
            rate=ask('Steuersatz der Gruppe (%)')
            try: rate=float(rate.replace(',','.'))
            except ValueError: raise WorkflowError('Steuersatz muss eine Zahl sein')
            groups.append(dict(vat_rate=rate,**{k:money('Steuergruppe '+k) for k in ('gross','net','vat')}))
            if not yes('Weitere Steuergruppe?'): break
        p['vat_breakdown']=groups;p['vat_rate']=None
    elif p['tax_treatment']=='no_vat_shown': p['vat_rate']=None;p.pop('vat_breakdown',None)
    else:
        raw=ask('Dokumentierter Steuersatz (%)',p.get('vat_rate'),optional=True)
        p['vat_rate']=float(raw.replace(',','.')) if raw else None;p.pop('vat_breakdown',None)
    p['category']=choice('Kategorie',CATEGORIES,p.get('category') or 'other')
    p['supplier_country']=ask('Lieferantenland (ISO-Code)',p.get('supplier_country') or 'DE').upper()
    p['business_use']=choice('Betriebliche Nutzung',('business','mixed','unclear'),p.get('business_use') or 'business')
    p['tax_review_required']=yes('Steuerliche Zuordnung noch offen?',p.get('tax_review_required',False) or p['supplier_country']!='DE' or p['tax_treatment']=='special_review')
    if p['tax_review_required']: p['tax_review_note']=ask('Was muss steuerlich geprüft werden?',p.get('tax_review_note'))
    if p.get('document_type')=='supplier_credit': p['correction_reason']=ask('Grund der Lieferanten-Korrektur',p.get('correction_reason'))
    if yes('Tatsächliche Zahlung/Erstattung bereits anhand eines Nachweises geprüft?'):
        p['pay_date']=day('Zahlungsdatum',p.get('pay_date'));p['paid_amount']=money('Bezahlter/erstatteter Betrag',p.get('paid_amount') or p['gross'],True)
        p['payment_evidence']=ask('Konkreter Zahlungsnachweis')
    else:
        p['pay_date']=None;p.pop('paid_amount',None);p.pop('payment_evidence',None)
    p['verification_basis']=ask('Wie wurde der Beleg geprüft?',p.get('verification_basis'))
    p['duplicate_review']=ask('Falls mögliche Dublette: Begründung (sonst leer)',optional=True)
    return confirm(validate_metadata(p))


def payment(record_id):
    print('Vorzeichen: Rechnungseingang/Lieferanten-Erstattung positiv; bezahlte Ausgabe/Kundenrückzahlung negativ.')
    print('Die manuelle Zahlungsquelle ersetzt importierte Zahlungen dieses Belegs. Alle tatsächlichen Teilzahlungen einzeln ergänzen.')
    p=dict(record_id=record_id,amount=money('Tatsächlicher Zahlungsbetrag'),date=day('Zahlungsdatum'),
           external_reference=ask('Eindeutige Zahlungsreferenz (z. B. Kontoauszug + Zeile)'),evidence=ask('Geprüfter Nachweis'))
    p['source_complete']=yes('Sind damit alle Zahlungen dieses Belegs vollständig zugeordnet?')
    return confirm(p,True)


def adjustment(catalog, rid, kind):
    from autobookkeeping.adjustments import original_view, remaining_positions
    original=original_view(catalog,rid)
    p={'reason':ask('Grund der Korrektur')}
    if kind=='partial_refund':
        allocations=[]
        for i,(position,balance) in enumerate(zip(original['positions'],remaining_positions(catalog,original))):
            if balance['gross']<=0: continue
            value=money(f"Position {i+1}: {position['title']} (noch {balance['gross']} EUR) – Minderung",'0.00')
            if Decimal(value): allocations.append({'position_index':i,'gross':value})
        p['allocations']=allocations
    elif kind=='correction':
        changes={}
        for key,label in [('buyer.name','Empfängername'),('buyer.street','Straße'),('buyer.postal_code','PLZ'),('buyer.city','Ort'),('delivery_date','Lieferdatum')]:
            value=ask(label+' ändern (leer = unverändert)',optional=True)
            if value: changes[key]=value
        p['changes']=changes
    return confirm(p)


def manual_invoice():
    p={'reference':ask('Eindeutige eigene Auftragsreferenz (für Dublettenprüfung)'),'verification_basis':ask('Quelle und Prüfung des Verkaufs')}
    p['buyer']={k:ask(label) for k,label in [('name','Käufername'),('street','Straße / Hausnummer'),('postal_code','PLZ'),('city','Ort')]}
    p['buyer'].update(country='Deutschland',country_iso='DE')
    p['delivery_date']=day('Liefer-/Leistungsdatum')
    p['positions']=[]
    while True:
        title=ask('Artikel / Leistung')
        while True:
            raw=ask('Menge','1')
            if raw.isdecimal() and int(raw)>0:quantity=int(raw);break
            print('Bitte eine positive ganze Menge eingeben.')
        p['positions'].append({'title':title,'quantity':quantity,'unit':'Stk.','unit_gross':money('Einzelpreis brutto',positive=True)})
        if not yes('Weitere Position (auch Versand kann eine Position sein)?'): break
    print('Steuersätze werden aus dem Absenderprofil bzw. den ausdrücklich gewählten Sätzen übernommen. Zahlung wird später separat zugeordnet.')
    return confirm(p)


def profile():
    print('Absenderprofil für deutsche Kleinunternehmer. Regelbesteuerung anschließend separat prüfen und freigeben.')
    p={key:ask(label) for key,label in [('name','Name / Firma'),('street','Straße / Hausnummer'),('postal_code','PLZ'),('city','Ort'),('tax_number','Steuernummer')]}
    p.update(country_iso='DE',small_business=True,tax_note='Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.',introduction=ask('Einleitung','Vielen Dank für Ihren Einkauf.'))
    return confirm(p)
