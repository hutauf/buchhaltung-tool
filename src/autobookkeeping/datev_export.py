"""Read-only EXTF 700/13 cash export for the reviewed SKR03 EÜR 2026 profile."""
from __future__ import annotations

import re
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from autobookkeeping.archive import atomic, encoded, outside, sha
from autobookkeeping.cashflow import document_flows, cents
from autobookkeeping.homeoffice import public_allowances
from autobookkeeping.local_invoices import WorkflowError

SUPPORTED_YEARS = (2026,)
PROFILE = 'SKR03-EUER-KU-2026-v1'
ACCOUNTS = {'income': '8192', 'software_subscriptions': '4806', 'postage': '4910',
            'office': '4930', 'goods': '3349', 'marketplace_fees': '4900', 'other': '4900',
            'unassigned': '4900', 'homeoffice': '4287'}
CONTRA = '1371'  # Non-profit EÜR clearing; deliberately no fictional bank balance.
SOURCES = [
    'https://developer.datev.de/de/file-format/details/datev-format/format-description/header',
    'https://developer.datev.de/de/file-format/details/datev-format/format-description/booking-batch',
    'https://developer.datev.de/de/file-format/details/datev-format/format-description/sample-data',
    'https://www.datev.de/web/de/shop/produkt-details/kontenrahmen-skr-03-4-absatz-3-estg-11079',
    'https://www.datev.de/dnlexom/v2/content/files/st63581358731_de.pdf',
]
# Official format-13 column order (including unpopulated optional fields).
COLUMNS = ('Umsatz (ohne Soll/Haben-Kz);Soll/Haben-Kennzeichen;WKZ Umsatz;Kurs;Basis-Umsatz;WKZ Basis-Umsatz;'
    'Konto;Gegenkonto (ohne BU-Schlüssel);BU-Schlüssel;Belegdatum;Belegfeld 1;Belegfeld 2;Skonto;Buchungstext;'
    'Postensperre;Diverse Adressnummer;Geschäftspartnerbank;Sachverhalt;Zinssperre;Beleglink;'
    + ';'.join(f'Beleginfo - {part} {n}' for n in range(1, 9) for part in ('Art', 'Inhalt')) +
    ';KOST1 - Kostenstelle;KOST2 - Kostenstelle;Kost-Menge;EU-Land u. UStID (Bestimmung);EU-Steuersatz (Bestimmung);'
    'Abw. Versteuerungsart;Sachverhalt L+L;Funktionsergänzung L+L;BU 49 Hauptfunktionstyp;BU 49 Hauptfunktionsnummer;'
    'BU 49 Funktionsergänzung;' +
    ';'.join(f'Zusatzinformation{ " - " if part == "Art" else "- "}{part} {n}' for n in range(1, 21) for part in ('Art', 'Inhalt')) +
    ';Stück;Gewicht;Zahlweise;Forderungsart;Veranlagungsjahr;Zugeordnete Fälligkeit;Skontotyp;Auftragsnummer;Buchungstyp;'
    'USt-Schlüssel (Anzahlungen);EU-Land (Anzahlungen);Sachverhalt L+L (Anzahlungen);EU-Steuersatz (Anzahlungen);'
    'Erlöskonto (Anzahlungen);Herkunft-Kz;Buchungs GUID;KOST-Datum;SEPA-Mandatsreferenz;Skontosperre;Gesellschaftername;'
    'Beteiligtennummer;Identifikationsnummer;Zeichnernummer;Postensperre bis;Bezeichnung SoBil-Sachverhalt;'
    'Kennzeichen SoBil-Buchung;Festschreibung;Leistungsdatum;Datum Zuord. Steuerperiode;Fälligkeit;Generalumkehr (GU);'
    'Steuersatz;Land;Abrechnungsreferenz;BVV-Position;EU-Land u. UStID (Ursprung);EU-Steuersatz (Ursprung);Abw. Skontokonto').split(';')
TEXT_FIELDS = {1, 2, 10, 13, 20, 21, 22, 23, 24, 25, 41}
HEADER_TEXT_FIELDS = {0, 3, 7, 8, 9, 16, 17, 21, 23, 26, 29, 30}
REASONS = {
    'tax_scope': 'Kleinunternehmer-Steuerstatus fehlt oder widerspricht den Beträgen.',
    'special_tax': 'Steuerlicher Sonderfall oder ausländischer Eingangsbeleg nicht automatisch kontiert.',
    'private_share': 'Betrieblicher Anteil ist ungeklärt.',
    'original_missing': 'Originalbeleg fehlt.',
    'payment_missing': 'Keine verwertbare Zahlung erfasst.',
    'payment_unclear': 'Zahlungsquelle unvollständig oder widersprüchlich.',
    'ebay_availability': 'Nur eBay-Käuferzahlung; tatsächliche Verfügbarkeit noch nicht zugeordnet.',
    'unsupported': 'Belegart oder Währung wird nicht unterstützt.',
    'number': 'Belegbetrag oder Zahlungsbetrag ist ungültig.',
}


def small_business(row):
    flags = (row.get('small_business'), (row.get('source_detail') or {}).get('smallBusiness'))
    return any(value is True for value in flags) and not any(value is False for value in flags)


def projection(catalog):
    """Allowlisted financial data only: no names, source IDs, free text or paths."""
    entries, issues = [], []
    for rid, versions in catalog.get('records', {}).items():
        row = versions['current']; kind = row['kind']
        if kind == 'correction' or row.get('status') in ('draft', 'test_draft'): continue
        flows, warnings = document_flows(catalog, row)
        base = catalog.get('records', {}).get(row.get('original_id'), {}).get('current', row)
        buyer_country = (base.get('buyer') or {}).get('country_iso') or (
            ((base.get('source_detail') or {}).get('customerData') or {}).get('countryIso'))
        try: zero_vat = row.get('vat') is not None and cents(row['vat']) == 0
        except (ValueError, TypeError, ArithmeticError): zero_vat = False
        reason = None
        if kind not in ('invoice', 'credit_note', 'expense', 'expense_credit') or row.get('currency', 'EUR') != 'EUR': reason = 'unsupported'
        elif row.get('coverage') != 'complete': reason = 'original_missing'
        elif kind in ('invoice', 'credit_note') and (not small_business(base) or not zero_vat): reason = 'tax_scope'
        elif (row.get('tax_review_required') or base.get('tax_review_required')
              or row.get('tax_treatment') == 'special_review' or base.get('tax_treatment') == 'special_review'
              or row.get('supplier_country') not in (None, 'DE') or base.get('supplier_country') not in (None, 'DE')
              or kind in ('invoice', 'credit_note') and buyer_country not in (None, 'DE')): reason = 'special_tax'
        elif base.get('business_use') in ('mixed', 'unclear') or row.get('business_use') in ('mixed', 'unclear'): reason = 'private_share'
        elif any(w in warnings for w in ('Unklare oder doppelte Zahlung in Quelldaten',
                 'Zahlungsdatum oder Betrag unvollständig', 'Zahlungszuordnung noch nicht als vollständig bestätigt',
                 'Quell-Zahlungsstorno/Umgebung: mit tatsächlichem Zahlungsfluss abgleichen')):
            reason = 'payment_unclear'
        elif row.get('status') == 'cancelled' and any(f['origin'] != 'verified' for f in flows): reason = 'payment_unclear'
        if not flows:
            day = str(row.get('date') or '')[:10]
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
                issues.append({'record_ref': sha(rid.encode())[:20], 'date': day, 'flow_ref': None,
                               'amount_cents': None, 'reason': reason or 'payment_missing'})
        for flow in flows:
            problem = reason or ('ebay_availability' if flow['origin'] == 'ebay_paid' else None)
            if type(flow['amount_cents']) is not int or not 0 < abs(flow['amount_cents']) <= 999999999999: problem = 'number'
            if problem:
                issues.append({'record_ref': sha(rid.encode())[:20], 'date': flow['date'], 'flow_ref': flow['ref'],
                               'amount_cents': flow['amount_cents'], 'reason': problem}); continue
            category = 'income' if flow['bucket'] == 'income' else base.get('category') or row.get('category') or 'unassigned'
            if category not in ACCOUNTS: category = 'unassigned'
            number = str(row.get('document_number') or row.get('number') or '')
            # Invalid/private supplier numbering stays outside the anonymized projection.
            number = number if len(number) <= 36 and re.fullmatch(r'[0-9]+(?:-K[0-9]+)?', number) else 'B' + sha(rid.encode())[:20]
            amount = flow['amount_cents']
            entries.append({'ref': flow['ref'], 'record_ref': sha(rid.encode())[:20], 'date': flow['date'],
                'amount_cents': amount, 'bucket': flow['bucket'], 'category': category, 'account': ACCOUNTS[category],
                'contra': CONTRA, 'side': 'H' if amount > 0 else 'S',
                'number': number, 'origin': flow['origin'], 'batch': 'payments',
                'mapping_note': 'Sammelkonto; Feinzuordnung beim Empfänger.' if category in ('unassigned', 'marketplace_fees', 'other') else None})
    for value in public_allowances(catalog):
        if not value['amount_cents']: continue
        year = value['year']; reference = sha(f'homeoffice:{year}'.encode())[:20]
        entries.append({'ref': reference, 'record_ref': reference, 'date': f'{year}-12-31',
            'amount_cents': -value['amount_cents'], 'bucket': 'deduction', 'category': 'homeoffice',
            'account': ACCOUNTS['homeoffice'], 'contra': CONTRA, 'side': 'S', 'number': f'HO{year}',
            'origin': 'confirmed_allowance', 'batch': 'allowances', 'mapping_note': 'Jahrespauschale, kein Geldabfluss.'})
    return {'profile': PROFILE, 'supported_years': list(SUPPORTED_YEARS), 'entries': sorted(entries, key=lambda e: (e['date'], e['ref'])),
            'issues': sorted(issues, key=lambda e: (e['date'], e['record_ref'])), 'reasons': REASONS}


def identifiers(advisor, client):
    if not re.fullmatch(r'[1-9][0-9]{3,6}', str(advisor)) or not 1001 <= int(advisor) <= 9999999:
        raise WorkflowError('Echte DATEV-Beraternummer des Empfängers erforderlich (1001–9999999); keine Platzhalternummer verwenden')
    if not re.fullmatch(r'[1-9][0-9]{0,4}', str(client)):
        raise WorkflowError('Echte DATEV-Mandantennummer des Empfängers erforderlich (1–99999)')
    return int(advisor), int(client)


def private_projection(catalog):
    """CLI only: enrich rows from the encrypted source, never from dashboard HTML."""
    view = projection(catalog)
    records = {sha(rid.encode())[:20]: (rid, value['current'])
               for rid, value in catalog.get('records', {}).items()}
    for entry in [*view['entries'], *view['issues']]:
        if entry['record_ref'] not in records: continue  # Non-cash allowance.
        rid, row = records[entry['record_ref']]
        base = catalog['records'].get(row.get('original_id'), {}).get('current', row)
        customer = {}
        for candidate in (base, row):
            for section in ('source_record', 'source_detail'):
                customer.update((candidate.get(section) or {}).get('customerData') or {})
            customer.update(candidate.get('buyer') or {})
        if row['kind'] in ('invoice', 'credit_note'):
            name = customer.get('name') or ' '.join(str(customer.get(k) or '') for k in ('firstName', 'lastName')).strip()
            if not name: name = customer.get('companyName') or ''
        else:
            from autobookkeeping.receipts import supplier
            name = supplier(row) or supplier(base) or ''
        number = str(row.get('document_number') or row.get('number') or '')
        entry.update(record_id=rid, document_number=number, counterparty_name=str(name),
                     customer_data=customer if row['kind'] in ('invoice', 'credit_note') else {},
                     documents=list(row.get('documents', [])))
        if 'number' in entry and re.fullmatch(r'[A-Za-z0-9$&%*+\-/]{1,36}', number):
            entry['number'] = number
        if 'batch' in entry:
            transformations = []
            for key, value, limit in [('booking_text', name, 60), ('party_info', name, 210),
                                      ('number_info', number, 210)]:
                normalized = ' '.join(''.join(' ' if ord(c) < 32 or ord(c) == 127 else c for c in str(value)).split())
                converted = normalized.encode('cp1252', errors='replace').decode('cp1252')
                if normalized != str(value) or converted != normalized or len(converted) > limit:
                    transformations.append(key)
                entry[key] = converted[:limit]
            entry['text_adaptations'] = transformations
            entry['counterparty_missing'] = not bool(str(name).strip())
    return view


def line(values, text_fields):
    result = []
    for index, value in enumerate(values):
        if value is None: result.append(''); continue
        value = str(value)
        if any(ord(char) < 32 or ord(char) == 127 for char in value): raise ValueError('Steuerzeichen in DATEV-Feld')
        result.append('"' + value.replace('"', '""') + '"' if index in text_fields else value)
    return ';'.join(result) + '\r\n'


def fields(entry):
    amount = entry['amount_cents']
    if (type(amount) is not int or not 0 < abs(amount) <= 999999999999
        or entry['side'] != ('H' if amount > 0 else 'S')
        or entry['account'] != ACCOUNTS.get(entry['category']) or entry['contra'] != CONTRA
        or (entry['bucket'] == 'income') != (entry['category'] == 'income')
        or (entry['bucket'] == 'deduction') != (entry['category'] == 'homeoffice')):
        raise ValueError('Widersprüchliche DATEV-Betrags-/Kontenzuordnung')
    result = [None] * 125
    result[0] = f"{Decimal(abs(entry['amount_cents'])) / 100:.2f}".replace('.', ',')
    for index, value in {1: entry['side'], 2: 'EUR', 6: entry['account'], 7: entry['contra'],
         9: entry['date'][8:10] + entry['date'][5:7], 10: entry['number'],
         13: entry.get('booking_text') or 'EÜR ' + entry['category'] + ' ' + entry['ref'][:8],
         20: 'Archiv-Referenz', 21: entry['ref'], 41: 'K', 113: 0}.items(): result[index] = value
    if entry.get('party_info'): result[22:24] = ['Geschäftspartner', entry['party_info']]
    if entry.get('number_info'): result[24:26] = ['Original-Belegnummer', entry['number_info']]
    return result


def header(year, advisor, client, at, batch):
    return ['EXTF', 700, 21, 'Buchungsstapel', 13, at, None, 'RE', 'BuchhaltungTool', '',
            advisor, client, f'{year}0101', 4, f'{year}0101', f'{year}1231',
            f'EUER {year} ' + ('Pauschalen' if batch == 'allowances' else 'Zahlungen'), '',
            2 if batch == 'allowances' else 1, 30, 0, 'EUR', None, '', None, None, '03', None, None, '', 'KU EÜR']


def files(snapshot, year, advisor, client, source_sha256, at=None):
    advisor, client = identifiers(advisor, client)
    if snapshot.get('profile') != PROFILE: raise WorkflowError('DATEV-Exportprofil passt nicht; Datenansicht neu erzeugen')
    if type(year) is not int or year not in SUPPORTED_YEARS: raise WorkflowError('DATEV-Kontenprofil ist derzeit ausschließlich für 2026 geprüft')
    at = at or datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')[:17]
    if not re.fullmatch(r'20\d{15}', at): raise ValueError('Ungültiger Exportzeitpunkt')
    entries = [e for e in snapshot['entries'] if e['date'].startswith(str(year) + '-')]
    if not entries: raise WorkflowError('Keine exportierbaren Vorgänge im gewählten Jahr; Begleitbericht prüfen')
    issues = [i for i in snapshot['issues'] if i['date'].startswith(str(year) + '-')]
    result = {}
    for batch in ('payments', 'allowances'):
        group = [e for e in entries if e['batch'] == batch]
        if not group: continue
        if len(group) > 99999: raise WorkflowError('DATEV-Stapel darf höchstens 99999 Buchungen enthalten')
        csv_data = line(header(year, advisor, client, at, batch), HEADER_TEXT_FIELDS)
        csv_data += line(COLUMNS, set(range(125)))
        csv_data += ''.join(line(fields(entry), TEXT_FIELDS) for entry in group)
        data = csv_data.encode('cp1252', errors='strict')
        from autobookkeeping.datev_validation import validate
        validate(data)
        result[f'EXTF_{"Pauschalen" if batch == "allowances" else "Buchungsstapel"}_{year}.csv'] = data
    report = {'version': 2, 'year': year, 'profile': PROFILE, 'source_sha256': source_sha256,
        'created_at': at, 'advisor': advisor, 'client': client, 'entries': entries, 'excluded': issues,
        'complete_for_recorded_year': not issues, 'is_complete_business_eur': False,
        'income_cents': sum(e['amount_cents'] for e in entries if e['bucket'] == 'income'),
        'expense_cents': -sum(e['amount_cents'] for e in entries if e['bucket'] == 'expense'),
        'allowance_cents': -sum(e['amount_cents'] for e in entries if e['bucket'] == 'deduction'),
        'sources': SOURCES, 'validation': 'Lokale Feld-/Strukturprüfung; kein Importtest in einer DATEV-Anwendung.',
        'notes': ['Nur tatsächliche erfasste Zahlungsbewegungen; Rechnungen werden nicht zusätzlich als Umsatz exportiert.',
            'Homeoffice separat als bestätigte Jahrespauschale, nicht als Zahlung.',
            'Bruttoaufwand ohne Vorsteuerabzug; keine automatische Reverse-Charge-/Sondersteuerverarbeitung.',
            'Gegenkonto 1371 ist ein neutrales EÜR-Verrechnungskonto, kein Bankabgleich.',
            'Keine Festschreibung beim Import angefordert. Jeder erneute Import kann Doppelbuchungen erzeugen.',
            'Nummern, SKR03 und Kontenfunktionen müssen zum Empfängerbestand passen. Keine DATEV-Zertifizierung.',
            'Geschäftspartner im Buchungstext (60 Zeichen) und Beleginfo (210 Zeichen); keine Debitoren-/Kreditorenstammdaten oder OPOS.',
            'CP1252-Ersetzungen, Leerraumbereinigung und Kürzungen stehen unter text_adaptations; unveränderte Daten im UTF-8-Bericht und Archiv.',
            'Fehlende Namen werden als counterparty_missing markiert, nicht erfunden.']}
    result['exportbericht.json'] = encoded(report)
    result['LESEN.txt'] = ('DATEV-Export für Kleinunternehmer-EÜR 2026\r\n\r\n' + '\r\n'.join(report['notes']) +
        f'\r\n\r\n{len(entries)} Exportzeilen, {len(issues)} nicht übernommene Vorgänge.\r\n' +
        'Auslassungen und Kontenzuordnung: exportbericht.json. Der CLI-Export enthält unter archiv/ alle Originale, Metadaten und Historien aller Jahre.\r\n' +
        'ACHTUNG: Personenbezogener Klartext. Geschützt aufbewahren und nur gezielt weitergeben; niemals ins Repository kopieren.\r\n' +
        report['validation']).encode('utf8')
    result['pruefsummen.json'] = encoded({name: sha(data) for name, data in result.items()})
    return result


def export(archive, year, advisor, client, output):
    archive.verify(); output = outside(archive.repo, Path(output))
    if output.exists(): raise WorkflowError('Exportordner muss neu sein')
    data = files(private_projection(archive.catalog()), year, advisor, client,
                 sha((archive.root / 'database.json.enc').read_bytes()))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.datev-export-', dir=output.parent) as temp:
        package = outside(archive.repo, Path(temp) / 'export')
        archive.export(package / 'archiv', str(year))
        for name, payload in data.items(): atomic(package / name, payload)
        # Include every original and metadata/history file, not just EXTF payloads.
        hashes = {p.relative_to(package).as_posix(): sha(p.read_bytes())
                  for p in sorted(package.rglob('*')) if p.is_file() and p != package / 'pruefsummen.json'}
        atomic(package / 'pruefsummen.json', encoded(hashes))
        outside(archive.repo, package).rename(outside(archive.repo, output))
    return {'ok': True, 'output': str(output), 'files': list(data), 'complete_archive_included': True,
            'data_changed': False, 'datev_application_tested': False}
