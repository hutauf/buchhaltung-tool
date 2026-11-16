import copy
import json

import pytest

from autobookkeeping.cashflow import document_flows
from autobookkeeping.local_invoices import WorkflowError
from autobookkeeping.local_preparation import prepare_external, adopt_preparation
from test_local_invoices import workspace


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_local_preparation_changes_no_repository_and_one_approval_includes_paid_expense(workspace, tmp_path):
    archive, workflow, order, checks = workspace
    workflow.activate('0900', '0900', True)
    original = snapshot(archive.repo)
    receipt = dict(order_id=order.order_id, gross='5.00', date='2011-01-10', vat_rate=0,
                   payee='SYNTHETIC CARRIER', product='Testpaket', cart_id='synthetic-cart',
                   verified=True, verification_basis='Synthetic receipt checked',
                   pay_date='2011-01-10', paid_amount='5.00', payment_evidence='Synthetic paid receipt')
    result = prepare_external(workflow, tmp_path / 'local', lambda staged:
        staged.prepare(order, checks, (receipt, b'%PDF-1.4 SYNTHETIC ORIGINAL')))
    assert snapshot(archive.repo) == original
    assert result['archived'] is False and result['number_reserved'] is False
    assert (tmp_path / 'local/rechnung.pdf').exists()
    assert (tmp_path / 'local/rechnung.xml').exists()
    path = tmp_path / 'local/vorbereitung.json'
    revision = result['preparation_revision']
    with pytest.raises(WorkflowError, match='Bündelfreigabe'):
        adopt_preparation(workflow, path, revision, order, False)
    assert snapshot(archive.repo) == original
    adopted = adopt_preparation(workflow, path, revision, order, True)
    assert adopted['revision'] == result['revision']
    assert adopt_preparation(workflow, path, revision, order, True)['adopted'] is False
    issued = workflow.issue(adopted['id'], adopted['revision'], '0901', order, True)
    expense = workflow.expense(issued['id'], adopted['receipt_candidate_sha256'], True)
    catalog = archive.catalog()
    row = catalog['records'][expense['expense_id']]['current']
    flows, warnings = document_flows(catalog, row)
    assert not warnings and len(flows) == 1
    assert flows[0]['amount_cents'] == -500 and flows[0]['date'] == '2011-01-10'
    assert row['payment_evidence'] == receipt['payment_evidence']


def test_stale_or_changed_local_files_never_enter_archive(workspace, tmp_path):
    archive, workflow, order, checks = workspace
    result = prepare_external(workflow, tmp_path / 'local', lambda staged: staged.prepare(order, checks))
    original = snapshot(archive.repo)
    path = tmp_path / 'local/vorbereitung.json'
    changed = copy.deepcopy(order)
    changed.shipping_address.name = 'DIFFERENT SYNTHETIC BUYER'
    with pytest.raises(WorkflowError, match='Verkaufsdaten'):
        adopt_preparation(workflow, path, result['preparation_revision'], changed, True)
    with pytest.raises(WorkflowError, match='Revision'):
        adopt_preparation(workflow, path, '0' * 64, order, True)
    plan = json.loads(path.read_bytes())
    document = tmp_path / 'local' / next(iter(plan['files'].values()))['file']
    document.write_bytes(b'%PDF-1.4 ALTERED')
    with pytest.raises(WorkflowError, match='Original'):
        adopt_preparation(workflow, path, result['preparation_revision'], order, True)
    assert snapshot(archive.repo) == original


def test_prepare_target_inside_repo_is_rejected(workspace):
    archive, workflow, order, checks = workspace
    with pytest.raises(ValueError, match='außerhalb'):
        prepare_external(workflow, archive.repo / 'local', lambda staged: staged.prepare(order, checks))


def test_external_batch_allows_unreserved_number_sequence_to_advance(workspace, tmp_path):
    archive, workflow, order, checks = workspace
    workflow.activate('0900', '0900', True)
    result = prepare_external(workflow, tmp_path / 'local', lambda staged: staged.prepare(order, checks))
    different = copy.deepcopy(order)
    different.order_id = 'different-synthetic-sale'
    different.sales_record_number = '9999'
    different.items[0].transaction_id = 'different-synthetic-transaction'
    draft = workflow.prepare(different, checks)
    workflow.issue(draft['id'], draft['revision'], '0901', different, True)
    adopted = adopt_preparation(workflow, tmp_path / 'local/vorbereitung.json',
                                result['preparation_revision'], order, True)
    assert adopted['proposed_number'] == '0902'
    assert workflow.issue(adopted['id'], adopted['revision'], '0902', order, True)['number'] == '0902'


def test_cli_local_only_disables_publication(workspace, tmp_path, monkeypatch):
    import runpy
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    archive, workflow, order, checks = workspace
    original = snapshot(archive.root)
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/local_invoice.py'))
    class NoPublication:
        enabled = False
        def __init__(self, *args, enabled, **kwargs):
            assert enabled is False
        def __enter__(self): return self
        def __exit__(self, *args): return False
    module['main'].__globals__.update(data_root=lambda: archive.repo, Archive=lambda _: archive,
        Publication=NoPublication, load_settings=lambda: object(), read_checks=lambda *args: checks,
        EbayTradingClient=lambda _: SimpleNamespace(get_order=lambda _: order))
    monkeypatch.setattr(sys, 'argv', ['local_invoice.py', 'prepare', order.order_id,
                        '--local-only', '--output', str(tmp_path / 'external')])
    assert module['main']()['archived'] is False
    assert snapshot(archive.root) == original
