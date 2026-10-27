"""Invalidate erroneous expenses without deleting source records or inventing refunds."""
from __future__ import annotations

import copy
from datetime import datetime

from autobookkeeping.archive import encoded, sha
from autobookkeeping.local_invoices import WorkflowError, now


def invalidated(catalog, record_id):
    return record_id in catalog.get('expense_invalidations', {})


def validate(catalog):
    for rid, entry in catalog.get('expense_invalidations', {}).items():
        try:
            timestamp = datetime.fromisoformat(entry.get('at', ''))
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Ungültiger Zeitpunkt der Ausgaben-Ungültigkeitskennzeichnung') from None
        row = catalog.get('records', {}).get(rid, {}).get('current', {})
        original = entry.get('record_at_invalidation', {})
        if (row.get('kind') != 'expense' or original.get('id') != rid or original.get('kind') != 'expense'
                or entry.get('record_sha256') != sha(encoded(original))
                or not isinstance(entry.get('reason'), str) or not entry['reason'].strip()
                or entry.get('approved') is not True
                or timestamp.tzinfo is None):
            raise ValueError('Ungültige Ausgaben-Ungültigkeitskennzeichnung')


def invalidate(workflow, record_ids, reason, approved):
    if not approved or not isinstance(reason, str) or not reason.strip():
        raise WorkflowError('Konkrete Ausgaben und Begründung müssen zum Ungültigerklären freigegeben sein')
    ids = list(dict.fromkeys(record_ids))
    if not ids: raise WorkflowError('Mindestens eine bereits erfasste Ausgabe angeben')
    workflow.archive.verify()
    before = workflow.archive.catalog()
    after = copy.deepcopy(before)
    registry = after.setdefault('expense_invalidations', {})
    added = []
    for rid in ids:
        row = before.get('records', {}).get(rid, {}).get('current', {})
        if row.get('kind') != 'expense' or row.get('status') in ('draft', 'test_draft'):
            raise WorkflowError('Nur bereits erfasste Ausgaben können ungültig erklärt werden')
        if any(v['current'].get('original_id') == rid and v['current'].get('kind') == 'expense_credit'
               for v in before['records'].values()):
            raise WorkflowError('Verknüpfte Lieferanten-Korrekturen zuerst gesondert klären')
        if rid in registry:
            if registry[rid]['reason'] != reason.strip():
                raise WorkflowError('Ausgabe bereits ungültig; vorhandene Begründung bleibt erhalten')
            continue
        from autobookkeeping.cashflow import document_flows
        flows, _ = document_flows(before, row)
        registry[rid] = {'at': now(), 'reason': reason.strip(), 'approved': True,
                         'record_at_invalidation': copy.deepcopy(row), 'record_sha256': sha(encoded(row)),
                         'cash_flows_at_invalidation': flows}
        added.append(rid)
    if added:
        validate(after)
        workflow.commit(before, after, {})
    return {'ok': True, 'changed': bool(added), 'invalidated': added,
            'records_preserved': True, 'refund_created': False}
