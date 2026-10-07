"""Read-only sales comparison; evidence is encrypted, never a fees import."""
import copy
from collections import Counter
from decimal import Decimal
from autobookkeeping.archive import encoded, sha
from autobookkeeping.local_invoices import now, record_context, WorkflowError

STATES = {'unpaid', 'matched', 'amount_mismatch', 'ambiguous', 'draft',
          'external_reference', 'missing_invoice', 'private', 'missing_original'}


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
            if len(found) > 1 or len(links) > 1: state = 'ambiguous'
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


def public_status(catalog):
    values = catalog.get('ebay_reconciliations', {}).values()
    latest = max(values, key=lambda r: r['at'], default=None)
    if not latest: return {'available': False}
    return {'available': True, 'at': latest['at'], 'days': latest['days'], 'pages': latest['pages'],
            'complete': latest['complete'], 'orders': latest['orders'],
            'counts': {k: v for k,v in latest['counts'].items() if k in STATES}}


def validate(catalog):
    for row in catalog.get('ebay_reconciliations', {}).values():
        if (row.get('scope') != 'sales_api_window' or row.get('complete') is not True
            or row.get('bank_reconciled') is not False or row.get('fees_imported') is not False
            or not 1 <= row['days'] <= 90 or row['pages'] < 1
            or len(row['rows']) != row['orders'] or dict(Counter(r['state'] for r in row['rows'])) != row['counts']
            or not set(row['counts']) <= STATES or any(n not in catalog['documents'] for n in row['documents'])):
            raise ValueError('eBay-Abgleichnachweis ist unvollständig oder widersprüchlich')
