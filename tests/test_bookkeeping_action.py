import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from autobookkeeping.archive import sha
from autobookkeeping.local_invoices import WorkflowError

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/bookkeeping_action.py'))


def test_opaque_reference_resolves_exactly_one_row():
    row = {'id': 'PRIVATE IDENTIFIER', 'status': 'test_draft', 'revision': '0' * 64}
    catalog = {'local_invoice_drafts': {'key': {'current': row}}}
    ref = sha(row['id'].encode())[:20]
    section, result = MODULE['resolve'](catalog, ref)
    assert section == 'local_invoice_drafts' and result == row
    with pytest.raises(WorkflowError): MODULE['resolve'](catalog, '0' * 20)
    catalog['records'] = {'other': {'current': row}}
    with pytest.raises(WorkflowError): MODULE['resolve'](catalog, ref)


@pytest.mark.parametrize('section,script,sub', [('local_invoice_drafts', 'local_invoice.py', 'issue'),
    ('local_adjustment_drafts', 'local_invoice.py', 'adjustment-issue'), ('local_expense_drafts', 'receipt.py', 'book')])
def test_finish_carries_the_exact_current_revision(section, script, sub):
    args = SimpleNamespace(action='finish', number='0901')
    row = {'id': 'PRIVATE IDENTIFIER', 'status': 'test_draft', 'revision': 'a' * 64}
    command = MODULE['command'](args, section, row)
    assert command[:3] == [script, sub, row['id']]
    assert command[command.index('--revision') + 1] == row['revision'] and command[-1] == '--approved'
    with pytest.raises(WorkflowError): MODULE['command'](args, 'records', row)


def test_supplier_credit_import_resolves_original_locally_without_booking():
    args=SimpleNamespace(action='supplier-credit-inspect',file=Path('SYNTHETIC-CREDIT.pdf'))
    row={'id':'PRIVATE IDENTIFIER','kind':'expense'}
    assert MODULE['command'](args,'records',row)==['receipt.py','inspect','SYNTHETIC-CREDIT.pdf','--original-id',row['id']]
    with pytest.raises(WorkflowError):MODULE['command'](args,'local_expense_drafts',row)
