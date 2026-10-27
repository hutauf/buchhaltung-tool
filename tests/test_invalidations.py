import copy
import json
import runpy
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from autobookkeeping.archive import Archive, encoded
from autobookkeeping.local_invoices import LocalInvoices, WorkflowError
from autobookkeeping.invalidations import invalidate, validate
from autobookkeeping.cashflow import document_flows, record_cash
from autobookkeeping.homeoffice import eur_summary
from autobookkeeping.dashboard import projection, html
from autobookkeeping.datev_export import projection as datev_projection, private_projection
from autobookkeeping.annual_report import report

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    repo = tmp_path/'repo'; repo.mkdir()
    archive = Archive(repo, 'synthetic-password'); archive.init()
    pdf = tmp_path/'original.pdf'; pdf.write_bytes(b'%PDF-1.4 SYNTHETIC ORIGINAL')
    ids = []
    for n, amount in enumerate(('11.00', '7.00')):
        path = tmp_path/f'receipt-{n}.json'
        path.write_bytes(encoded({'source':'synthetic','source_id':str(n),'kind':'expense',
            'date':'2026-01-01','pay_date':'2026-01-02','status':'recorded','currency':'EUR',
            'gross':amount,'net':amount,'vat':'0.00','vat_rate':0,'category':'office',
            'payee':'SYNTHETIC SUPPLIER','number':f'TEST-{n}'}))
        ids.append(archive.import_local(path,[pdf])['record_id'])
    return archive, LocalInvoices(archive), ids


def test_invalidation_preserves_originals_and_changes_every_financial_view(setup,tmp_path):
    archive, workflow, ids = setup
    before = archive.catalog()
    originals = {name:archive.read(name) for name in before['documents']}
    assert eur_summary(before,2026)['cash_expenses_cents'] == 1800
    result = invalidate(workflow,ids,'PRIVATE SYNTHETIC REASON',True)
    after = archive.catalog()
    assert result['changed'] and not result['refund_created']
    assert before['records'] == after['records'] and before['documents'] == after['documents']
    assert all(archive.read(name)==content for name,content in originals.items())
    assert eur_summary(after,2026)['cash_expenses_cents'] == 0
    assert all(document_flows(after,v['current'])[0]==[] for v in after['records'].values())
    snapshot = projection(after,'0'*64)
    assert all(r['status']=='invalidated' and r['document_effect_cents']==0 and not r['flows'] for r in snapshot['rows'])
    rendered = html(snapshot,(ROOT/'scripts/dashboard_view.html').read_bytes())
    assert b'PRIVATE SYNTHETIC REASON' not in rendered
    assert len(datev_projection(after)['issues'])==2
    assert {r['reason'] for r in datev_projection(after)['issues']}=={'invalidated'}
    assert datev_projection(after)['entries']==[]
    assert all(r['invalidation']['reason']=='PRIVATE SYNTHETIC REASON' for r in private_projection(after)['issues'])
    annual=report(after,2026)
    assert annual['summary']['cash_expenses_cents']==0
    assert all(r['status']=='invalidated' and r['invalidation']['reason']=='PRIVATE SYNTHETIC REASON' for r in annual['records'])
    archive.export(tmp_path/'export')
    export_view=json.loads((tmp_path/'export/database.json').read_bytes())
    assert all(r['status']=='invalidated' and r['source_status']=='recorded'
               and r['invalidation']['reason']=='PRIVATE SYNTHETIC REASON' for r in export_view['records'])
    assert archive.verify()['audit']['status']=='verified'
    ciphertext=(archive.root/'database.json.enc').read_bytes()
    assert not invalidate(workflow,ids,'PRIVATE SYNTHETIC REASON',True)['changed']
    assert (archive.root/'database.json.enc').read_bytes()==ciphertext
    with pytest.raises(WorkflowError):invalidate(workflow,ids,'different reason',True)


def test_invalidation_is_atomic_requires_approval_and_survives_source_refresh(setup):
    archive, workflow, ids = setup;before=archive.catalog()
    for record_ids,reason,approved in ((ids,'reason',False),(ids,'',True),([], 'reason',True),([ids[0],'missing'],'reason',True)):
        with pytest.raises(WorkflowError):invalidate(workflow,record_ids,reason,approved)
        assert archive.catalog()==before
    invalidate(workflow,[ids[0]],'synthetic erroneous entry',True)
    before=archive.catalog();after=copy.deepcopy(before)
    after['records'][ids[0]]['history'].append(copy.deepcopy(after['records'][ids[0]]['current']))
    after['records'][ids[0]]['current']['source_record']['extra_source_metadata']='SYNTHETIC REFRESH'
    workflow.commit(before,after,{})
    current=archive.catalog()
    assert document_flows(current,current['records'][ids[0]]['current'])[0]==[]
    assert eur_summary(current,2026)['cash_expenses_cents']==700
    with pytest.raises(WorkflowError,match='Ungültige Ausgabe'):
        record_cash(workflow,{'record_id':ids[0],'amount':'-11.00','date':'2026-01-02',
            'external_reference':'SYNTHETIC PAYMENT','evidence':'SYNTHETIC SOURCE','source_complete':True},True)
    damaged=copy.deepcopy(current);damaged['expense_invalidations'][ids[0]]['record_at_invalidation']['gross']='99.00'
    with pytest.raises(ValueError):validate(damaged)


def test_dashboard_actions_keep_invalid_expenses_read_only_and_address_missing_originals(setup):
    archive, workflow, ids=setup
    invalidate(workflow,[ids[0]],'SYNTHETIC reason',True)
    snapshot=projection(archive.catalog(),'0'*64)
    node=shutil.which('node')
    if not node:pytest.skip('Node required')
    source=(ROOT/'scripts/dashboard_view.html').read_text(encoding='utf8')
    assert '<option value="invalidated">Ungültig · nicht berücksichtigt</option>' in source
    script='function commandsFor'+source.split('function commandsFor',1)[1].split("$('homeoffice-preview')",1)[0]
    program=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const context={python:'buchhaltung ',DATA:{source_sha256:'0'.repeat(64)},esc:String};vm.createContext(context);vm.runInContext(input.script,context);
const invalid=input.rows.find(r=>r.status==='invalidated'),valid=input.rows.find(r=>r.status!=='invalidated');
assert(!context.commandsFor(invalid).includes('expense-invalidate'));assert(!context.commandsFor(invalid).includes('payments'));
assert(context.commandsFor(valid).includes('expense-invalidate'));assert(context.commandsFor(valid).includes('--interactive'));
assert(!context.commandsFor({...invalid,coverage:'missing'}).includes('preview'));
"""
    subprocess.run([node,'-e',program],input=json.dumps({'script':script,'rows':snapshot['rows']}).encode(),capture_output=True,check=True,timeout=20)


def test_dashboard_invalidation_route_does_not_expose_record_id_in_html():
    script=runpy.run_path(str(ROOT/'scripts/bookkeeping_action.py'))
    args=SimpleNamespace(action='expense-invalidate',interactive=True)
    assert script['command'](args,'records',{'id':'SYNTHETIC-ID','kind':'expense'})==[
        'receipt.py','invalidieren','SYNTHETIC-ID','--interactive']
    with pytest.raises(WorkflowError):script['command'](args,'records',{'id':'SYNTHETIC-ID','kind':'invoice'})
