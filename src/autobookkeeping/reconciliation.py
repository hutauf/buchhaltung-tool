"""Read-only sales comparison; evidence is encrypted, never a fees import."""
import copy
from collections import Counter
from decimal import Decimal
from autobookkeeping.archive import encoded, sha
from autobookkeeping.local_invoices import now, record_context, WorkflowError

STATES = {'unpaid', 'matched', 'amount_mismatch', 'ambiguous', 'draft',
          'external_reference', 'missing_invoice', 'private', 'missing_original', 'adjusted'}
FINDINGS = STATES - {'unpaid', 'matched', 'private'}


def identity(row):
    return {str(x) for x in [row.get('order_id'), *row.get('order_id_aliases', [])] if x}


def matches(left, right):
    if left.get('sales_record_number') and right.get('sales_record_number'):
        if str(left['sales_record_number']) == str(right['sales_record_number']): return True
    if identity(left) & identity(right): return True
    def transactions(row):
        return {(str(p['item_id']), str(p['transaction_id'])) for p in row.get('positions', [])
                if p.get('item_id') and p.get('transaction_id')}
    # A shared title or just one position of a larger order is insufficient.
    a, b = transactions(left), transactions(right)
    return bool(a) and a == b


def compare(catalog, orders, checklist):
    results = []
    items = checklist.get('items', [])
    records = [v['current'] for v in catalog['records'].values() if v['current']['kind'] == 'invoice']
    drafts = [v['current'] for v in catalog.get('local_invoice_drafts', {}).values()
              if v['current']['status'] == 'test_draft']
    for order in orders:
        context = {'order_id': order.order_id, 'sales_record_number': order.sales_record_number,
                   'order_id_aliases': order.order_id_aliases,
                   'positions': [{'item_id': p.item_id, 'transaction_id': p.transaction_id} for p in order.items]}
        links = [i for i in items if matches(context, i)]
        found = []
        for row in records:
            related = [i for i in links if str(i.get('invoice_id')) == str(row.get('source_id'))
                       or i.get('local_invoice_id') == row['id']]
            if matches(context, record_context(row)) or related: found.append(row)
        state = 'unpaid' if order.paid_at is None else 'missing_invoice'
        if order.paid_at is not None:
            from autobookkeeping.adjustments import fully_cancelled, credits
            cancelled = [r for r in found if r.get('status') == 'cancelled' or fully_cancelled(catalog, r['id'])]
            active = [r for r in found if r not in cancelled]
            # A cancelled original plus its explicitly linked replacement is one chain.
            connected = {found[0]['id']} if found else set()
            while True:
                extended = connected | {r['id'] for r in found if r.get('replacement_of') in connected}
                extended |= {r['replacement_of'] for r in found if r['id'] in connected and r.get('replacement_of')}
                if extended == connected: break
                connected = extended
            chain = len(active) <= 1 and all(r['id'] in connected for r in found)
            adjusted = bool(cancelled or any(credits(catalog, r['id']) for r in found))
            if len(links) > 1 or len(found) > 1 and not (adjusted and chain): state = 'ambiguous'
            elif adjusted: state = 'adjusted'
            elif found:
                row = found[0]
                if row.get('currency', 'EUR') != order.currency or Decimal(str(row.get('gross'))) != Decimal(str(order.total_value)):
                    state = 'amount_mismatch'
                elif row.get('status') == 'draft': state = 'draft'
                elif row.get('coverage') != 'complete': state = 'missing_original'
                else: state = 'matched'
            elif any(matches(context, r) for r in drafts): state = 'draft'
            elif links:
                state = 'private' if links[0].get('status') == 'privat' else 'external_reference' if links[0].get('invoice_id') else 'missing_invoice'
        results.append(dict(context, state=state, currency=order.currency, gross=str(order.total_value),
                            paid_at=order.paid_at.isoformat() if order.paid_at else None,
                            created_at=order.created_at.isoformat() if order.created_at else None,
                            record_ids=[r['id'] for r in found]))
    return results


def scan(archive, client, checklist, days=90, save=False):
    archive.verify()
    orders = client.get_orders(days=days, limit=None)
    if not client.orders_complete: raise WorkflowError('Abgleich ohne vollständigen Seitenabruf gesperrt')
    before = archive.catalog()
    rows = compare(before, orders, checklist)
    at = now()
    result = {'at': at, 'days': days, 'window': client.order_window, 'checklist_sha256':sha(encoded(checklist)),
              'pages': len(client.order_pages), 'complete': True,
              'counts': dict(Counter(r['state'] for r in rows)), 'orders': len(rows), 'rows': rows,
              'scope': 'sales_api_window', 'bank_reconciled': False, 'fees_imported': False}
    if save:
        from autobookkeeping.local_invoices import LocalInvoices
        after = copy.deepcopy(before); scan_id = sha(encoded(result))
        documents = [] ; payloads = {}
        for payload, extension, role in [(encoded(result),'json','ebay_sales_check'),
                                        (encoded(checklist),'json','comparison_checklist'),
                                        *[(p,'xml','ebay_sales_api') for p in client.order_pages]]:
            name = f"{at[:4]}/Unterlagen/{sha(payload)}.{extension}.enc"
            documents.append(name)
            if name not in after['documents']:
                payloads[name] = payload
                after['documents'][name] = {'record_id': 'ebay-scan:'+scan_id, 'role': role,
                                           'sha256_plaintext': sha(payload), 'bytes_plaintext': len(payload)}
        after.setdefault('archive_evidence', {})['ebay-scan:'+scan_id] = {
            'date': at[:10], 'description': 'Read-only eBay sales API reconciliation',
            'verification_basis': 'All returned pages, seller orders, paid and unpaid', 'documents': documents}
        after.setdefault('ebay_reconciliations', {})[scan_id] = dict(result, documents=documents)
        LocalInvoices(archive).commit(before, after, payloads)
    return result


def finding_ref(row):
    return sha(encoded(row))[:20]


def findings(catalog):
    """Latest observation per sale, retained even outside subsequent API windows."""
    latest = []
    for scan_id, check in sorted(catalog.get('ebay_reconciliations', {}).items(), key=lambda p: (p[1]['at'], p[0])):
        for row in check['rows']:
            linked = [old for old in latest if matches(old['row'], row)]
            aliases = set(identity(row))
            for old in linked:
                aliases.update(identity(old['row']))
                latest.remove(old)
            context = dict(row, order_id_aliases=sorted(aliases - {row.get('order_id')}))
            anchor = linked[0]['scan_id'] if len(linked) == 1 and linked[0]['observed_row'] == row else scan_id
            latest.append({'scan_id': anchor, 'ref': finding_ref(row), 'row': context,
                           'observed_row': row, 'observed_at': check['at']})
    notes = list(catalog.get('ebay_reconciliation_notes', {}).values())
    result = []
    for entry in latest:
        if entry['row']['state'] not in FINDINGS: continue
        relevant = [note for note in notes if note['scan_id'] == entry['scan_id']
                    and note['row_sha256'] == sha(encoded(entry['observed_row']))]
        note = max(relevant, key=lambda n: n['sequence'], default=None)
        result.append(dict(entry, status='explained' if note and note['action'] == 'explain' else 'open', note=note))
    return sorted(result, key=lambda r: (r['observed_at'], r['ref']))


def explain(workflow, reference, reason, approved, reopen=False):
    """An explanation changes no API evidence, invoice or financial amount."""
    if not approved or not isinstance(reason, str) or not reason.strip():
        raise WorkflowError('Dokumentation der Abweichung benötigt den konkreten Grund und eine Bestätigung')
    workflow.archive.verify(); before = workflow.archive.catalog()
    candidates = [f for f in findings(before) if f['ref'] == reference]
    if len(candidates) != 1: raise WorkflowError('Abweichung fehlt oder ist inzwischen verändert; Fälle erneut anzeigen')
    found = candidates[0]
    if reopen and found['status'] != 'explained': raise WorkflowError('Abweichung ist bereits offen')
    after = copy.deepcopy(before)
    notes = after.setdefault('ebay_reconciliation_notes', {})
    body = {'sequence': len(notes) + 1, 'scan_id': found['scan_id'],
            'row_sha256': sha(encoded(found['observed_row'])), 'at': now(),
            'action': 'reopen' if reopen else 'explain', 'reason': reason.strip()}
    identifier = sha(encoded(body)); notes[identifier] = body
    workflow.commit(before, after, {})
    return {'ok': True, 'ref': reference, 'status': 'open' if reopen else 'explained',
            'financial_records_changed': False}


def public_status(catalog):
    values = catalog.get('ebay_reconciliations', {}).values()
    latest = max(values, key=lambda r: r['at'], default=None)
    if not latest: return {'available': False}
    cases = findings(catalog)
    return {'available': True, 'at': latest['at'], 'days': latest['days'], 'pages': latest['pages'],
            'complete': latest['complete'], 'orders': latest['orders'],
            'counts': {k: v for k,v in latest['counts'].items() if k in STATES},
            'open_findings': sum(f['status'] == 'open' for f in cases),
            'explained_findings': sum(f['status'] == 'explained' for f in cases),
            'findings': [{'ref': f['ref'], 'state': f['row']['state'], 'status': f['status']}
                         for f in cases]}


def validate(catalog):
    for row in catalog.get('ebay_reconciliations', {}).values():
        if (row.get('scope') != 'sales_api_window' or row.get('complete') is not True
            or row.get('bank_reconciled') is not False or row.get('fees_imported') is not False
            or not 1 <= row['days'] <= 90 or row['pages'] < 1
            or len(row['rows']) != row['orders'] or dict(Counter(r['state'] for r in row['rows'])) != row['counts']
            or not set(row['counts']) <= STATES or any(n not in catalog['documents'] for n in row['documents'])):
            raise ValueError('eBay-Abgleichnachweis ist unvollständig oder widersprüchlich')
    for sequence, (identifier, note) in enumerate(sorted(catalog.get('ebay_reconciliation_notes', {}).items(), key=lambda p: p[1]['sequence']), 1):
        check = catalog.get('ebay_reconciliations', {}).get(note['scan_id'])
        if (sha(encoded(note)) != identifier or note['sequence'] != sequence or not check
            or note['action'] not in ('explain', 'reopen') or not str(note.get('reason') or '').strip()
            or not any(sha(encoded(r)) == note['row_sha256'] and r['state'] in FINDINGS for r in check['rows'])):
            raise ValueError('Abweichungsvermerk hat keinen gültigen Originalbezug')
        from datetime import datetime
        if datetime.fromisoformat(note['at']).tzinfo is None:
            raise ValueError('Abweichungsvermerk benötigt einen Zeitpunkt mit Zeitzone')
