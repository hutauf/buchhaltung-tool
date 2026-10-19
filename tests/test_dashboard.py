import copy
import json
import runpy
import shutil
import subprocess
from pathlib import Path
import pytest
from autobookkeeping.archive import Archive, sha
from autobookkeeping.dashboard import projection, html, public_day, public_number, public_retention

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=runpy.run_path(str(ROOT/"scripts/build_bookkeeping_dashboard.py"))


def row():
    return {"id":"opaque-1","kind":"invoice","source":"imported","date":"2011-01-02","status":"paid",
            "number":"0001","gross":"119.00","net":"100.00","vat":"19.00","vat_rate":19,"year":"2011",
            "coverage":"complete","documents":[],"source_detail":{"payments":[{"id":1,"type":"payment","amount":119,"date":"2011-01-03T12:00:00Z"}]},
            "buyer":{"name":"PRIVATE <script>SECRET</script>"},"description":"PRIVATE PRODUCT", "order_id":"PRIVATE ORDER"}


@pytest.fixture
def staged_repo(tmp_path):
    repo=tmp_path/"repo";repo.mkdir()
    def git(*args):return subprocess.check_output(["git","-C",str(repo),*args],stderr=subprocess.PIPE)
    git("init");git("config","user.name","Synthetic Test");git("config","user.email","test@example.invalid");git("config","core.autocrlf","false")
    for name in SCRIPT["CODE"]:
        target=repo/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    (repo/".env").write_text("ENCRYPTION_PASSWORD=synthetic-password\n",encoding="utf8")
    archive=Archive(repo);archive.init();catalog=archive.catalog();catalog["records"]["opaque-1"]={"current":row(),"history":[]};archive.save_catalog(catalog)
    SCRIPT["build"](repo, tool=repo)
    git("add","buchhaltung","src","scripts","docs","dashboard.html");git("commit","-m","Synthetic initial archive")
    return repo,archive,git


def test_staged_snapshot_ignores_unstaged_database_and_is_deterministic(staged_repo):
    repo,archive,git=staged_repo
    catalog=archive.catalog();catalog["records"]["opaque-1"]["current"]["gross"]="130.00";archive.save_catalog(catalog)
    git("add","buchhaltung")
    staged_digest=sha((archive.root/"database.json.enc").read_bytes())
    catalog["records"]["opaque-1"]["current"]["gross"]="999.00";archive.save_catalog(catalog)
    SCRIPT["build"](repo,tool=repo,staged=True)
    snapshot=json.loads((repo/"dashboard.html").read_text(encoding="utf8").split('<script id="bookkeeping-data" type="application/json">')[1].split('</script>')[0])
    assert snapshot["source_sha256"]==staged_digest and snapshot["rows"][0]["gross_cents"]==13000
    first=(repo/"dashboard.html").read_bytes();SCRIPT["build"](repo,tool=repo,staged=True,check=True)
    assert (repo/"dashboard.html").read_bytes()==first
    assert git("diff","--name-only","--","buchhaltung").strip()


def test_incomplete_index_plaintext_and_manual_html_are_blocked(staged_repo):
    repo,archive,git=staged_repo
    archive.write("2011/Rechnungen/new.pdf.enc",b"%PDF-1.4 PRIVATE")
    git("add","buchhaltung/2011")
    with pytest.raises(ValueError,match="inventarisiert"):SCRIPT["build"](repo,tool=repo,staged=True)
    git("reset","--","buchhaltung/2011")
    (archive.root/"2011/Rechnungen/new.pdf.enc").unlink()
    (archive.root/"oops.pdf").write_bytes(b"PRIVATE PDF");git("add","buchhaltung/oops.pdf")
    with pytest.raises(ValueError,match="Klartextbeleg"):SCRIPT["build"](repo,tool=repo,staged=True)
    git("reset","--","buchhaltung/oops.pdf")
    (archive.root/"oops.pdf").unlink()
    catalog=archive.catalog();catalog["records"]["opaque-1"]["current"]["gross"]="130.00";archive.save_catalog(catalog)
    git("add","buchhaltung/database.json.enc","buchhaltung/manifest.json")
    (repo/"dashboard.html").write_text("USER EDIT",encoding="utf8")
    with pytest.raises(ValueError,match="überschrieben"):SCRIPT["build"](repo,tool=repo,staged=True)
    assert (repo/"dashboard.html").read_text()=="USER EDIT"


def test_partial_generator_edits_and_secret_staging_blocked(staged_repo):
    repo,archive,git=staged_repo
    helper=repo/"scripts/dashboard_view.html";helper.write_bytes(helper.read_bytes()+b'\n<!-- local edit -->')
    git("add","dashboard.html")
    # Force checking even when the index has no financial changes.
    with pytest.raises(ValueError,match="nicht vorgemerkte"):SCRIPT["build"](repo,tool=repo,staged=True,check=True)
    git("add",".env")
    with pytest.raises(ValueError,match="Passwort"):SCRIPT["build"](repo,tool=repo,staged=True)


def test_projection_and_script_injection_have_no_personal_fields():
    source=row();source.update(number='</script><script>PRIVATE_NUMBER</script>',date="PRIVATE DATE")
    catalog={"records":{"opaque-1":{"current":source,"history":[]}},"documents":{}}
    snapshot=projection(catalog,"0"*64);data=html(snapshot,(ROOT/"scripts/dashboard_view.html").read_bytes())
    assert b"PRIVATE" not in data and b"SECRET" not in data and b"source_detail" not in data
    assert snapshot["rows"][0]["number"] is None and snapshot["rows"][0]["date"] is None
    assert public_number("0901-K2")=="0901-K2" and public_day("2011-02-31") is None
    assert b"fetch(" not in data and b"https://" not in data and b"http://" not in data


def test_unknown_amount_not_silently_zero_and_trial_excluded():
    source=row();source.update(gross=None,net=None,vat=None)
    draft=dict(row(),id="draft",status="test_draft",gross="9999.00", revision="0"*64)
    catalog={"records":{"opaque-1":{"current":source,"history":[]}},"local_invoice_drafts":{"draft":{"current":draft,"history":[]}}}
    rows=projection(catalog,"0"*64)["rows"]
    assert next(r for r in rows if r["kind"]=="invoice")["gross_cents"] is None
    test=next(r for r in rows if r["kind"]=="draft");assert test["document_effect_cents"]==0 and test["flows"]==[]


def test_local_invoice_draft_without_kind_or_source_has_completion_number():
    draft = dict(row(), id="private-draft", status="test_draft", number=None, revision="0"*64)
    del draft["kind"]; del draft["source"]
    catalog = {"records": {}, "local_invoice_settings": {"last_service_number": "0900", "mode": "trial"},
               "local_invoice_drafts": {"private-draft": {"current": draft, "history": []}}}
    snapshot = projection(catalog, "0"*64); public = snapshot["rows"][0]
    assert public["proposed_number"] == "0901" and public["document_type"] == "invoice"
    assert snapshot["homeoffice_default_days"] == 210
    assert "private-draft" not in json.dumps(snapshot)


def test_actual_dashboard_filter_includes_cancelled_originals_without_reclassifying_them():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to execute the dashboard JavaScript')
    template = (ROOT/'scripts/dashboard_view.html').read_text(encoding='utf8')
    script = template.split('<script>')[1].split('function drawChart')[0]
    rows = [dict(kind=kind, status=status, number=str(i), date='2011-01-02', flows=[], warnings=[],
                 coverage='complete', expense_category=None)
            for i, (kind, status) in enumerate([
                ('invoice','paid'), ('invoice','cancelled'), ('invoice','locally_cancelled'),
                ('invoice','partially_credited'), ('credit_note','issued'), ('expense','cancelled')])]
    program = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const controls={};
for(const key of ['year','kind','category','quality','search'])controls[key]={value:key==='search'?'':'all'};
controls['bookkeeping-data']={textContent:JSON.stringify({rows:input.rows})};
const context={document:{getElementById:id=>controls[id]},console};
vm.createContext(context);
vm.runInContext(input.script,context);
function filter(kind,quality='all',year='all'){
 controls.kind.value=kind;controls.quality.value=quality;controls.year.value=year;
 return Array.from(vm.runInContext('scopeRows().map(row=>row.number).sort()',context));
}
assert.deepStrictEqual(filter('credit_note'),['1','2','3','4']);
assert.deepStrictEqual(filter('invoice'),['0','1','2','3']);
assert.deepStrictEqual(filter('credit_note','cancelled'),['1','2']);
assert.deepStrictEqual(filter('credit_note','all','2012'),[]);
assert.deepStrictEqual(filter('expense'),['5']);
assert.deepStrictEqual(JSON.parse(controls['bookkeeping-data'].textContent).rows,input.rows);
"""
    subprocess.run([node,'-e',program],input=json.dumps({'script':script,'rows':rows}).encode(),
                   capture_output=True,check=True,timeout=15)


def test_retention_projection_preserves_later_event_horizons_without_document_paths():
    from autobookkeeping.retention import report
    name='PRIVATE_ORIGINAL_PATH.pdf.enc'
    source=dict(row(), documents=[name])
    catalog={'records':{'opaque-1':{'current':source,'history':[]}},
             'documents':{name:{},'PRIVATE_UNKNOWN_PATH.enc':{}},
             'cash_events':{'synthetic-payment':{'record_id':'opaque-1','date':'2012-01-01'}},
             'cash_event_voids':{'synthetic-payment':{'at':'2013-01-01'}}}
    public=projection(catalog,'0'*64)
    assert public['retention']=={'retention_years':11,'documents':2,'unknown':1,
                                'groups':[{'earliest_review':'2025-01-01','documents':1}]}
    assert report(catalog,'2024-12-31')['documents'][0]['earliest_review']=='2025-01-01'
    assert 'PRIVATE' not in json.dumps(public)
    assert public_retention({})=={'retention_years':11,'documents':0,'unknown':0,'groups':[]}


def test_offline_retention_javascript_uses_berlin_day_and_exact_year_boundary():
    node=shutil.which('node')
    if not node:pytest.skip('Node is needed to execute the dashboard JavaScript')
    script=(ROOT/'scripts/dashboard_view.html').read_text(encoding='utf8').split('<script>')[1].split('function drawChart')[0]
    program=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const controls={year:{},'bookkeeping-data':{textContent:JSON.stringify({rows:[]})}};
const context={document:{getElementById:id=>controls[id]}};vm.createContext(context);
vm.runInContext(input.script,context);
const policy={documents:4,unknown:1,groups:[{earliest_review:'2023-01-01',documents:2},{earliest_review:'2024-01-01',documents:1}]};
context.policy=policy;
const counts=day=>JSON.parse(JSON.stringify(vm.runInContext(`retentionCounts(policy,'${day}')`,context)));
assert.deepStrictEqual(counts('2022-12-31'),{review:0,retained:3,unknown:1});
assert.deepStrictEqual(counts('2023-01-01'),{review:2,retained:1,unknown:1});
assert.deepStrictEqual(counts('2024-01-01'),{review:3,retained:0,unknown:1});
assert.strictEqual(vm.runInContext("retentionToday(new Date('2022-12-31T23:30:00Z'))",context),'2023-01-01');
assert.strictEqual(vm.runInContext("retentionToday(new Date('2022-12-31T22:30:00Z'))",context),'2022-12-31');
assert.strictEqual(vm.runInContext("retentionToday(new Date('2023-06-30T22:30:00Z'))",context),'2023-07-01');
"""
    subprocess.run([node,'-e',program],input=json.dumps({'script':script}).encode(),
                   capture_output=True,check=True,timeout=15)


def test_full_dashboard_initializes_and_recalculates_retention_without_cli():
    import re
    node=shutil.which('node')
    if not node:pytest.skip('Node is needed to execute the dashboard JavaScript')
    template=(ROOT/'scripts/dashboard_view.html').read_text(encoding='utf8')
    script=template.split('<script>')[1].split('</script>')[0]
    program=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const input=JSON.parse(fs.readFileSync(0,'utf8')),controls={};
for(const id of input.ids)controls[id]={value:['kind','category','quality'].includes(id)?'all':'',events:{},addEventListener(type,fn){this.events[type]=fn;}};
controls['bookkeeping-data'].textContent=JSON.stringify({rows:[],gaps:[],source_sha256:'0'.repeat(64),retention:{documents:4,unknown:1,groups:[{earliest_review:'2023-01-01',documents:2},{earliest_review:'2024-01-01',documents:1}]}});
const context={document:{getElementById:id=>controls[id]}};vm.createContext(context);
vm.runInContext(input.script,context);
assert.strictEqual(controls['retention-asof'].value,vm.runInContext('retentionToday()',context));
controls['retention-asof'].value='2022-12-31';controls['retention-asof'].events.change();
assert(controls['retention-status'].textContent.includes('3 weiter aufbewahren · 0 zur manuellen Fristprüfung · 1 mit ungeklärter Fristgrundlage'));
controls['retention-asof'].value='2023-01-01';controls['retention-asof'].events.change();
assert(controls['retention-status'].textContent.includes('1 weiter aufbewahren · 2 zur manuellen Fristprüfung · 1 mit ungeklärter Fristgrundlage'));
assert(controls['retention-rows'].innerHTML.includes('Manuell prüfen'));
assert(controls['retention-rows'].innerHTML.includes('Fristgrundlage klären'));
const before=controls['retention-status'].textContent;
controls.kind.value='invoice';controls.kind.events.change();
assert.strictEqual(controls['retention-status'].textContent,before);
controls['retention-asof'].value='';controls['retention-asof'].events.change();
assert.strictEqual(controls['retention-rows'].innerHTML,'');
controls['retention-today'].onclick();
assert.strictEqual(controls['retention-asof'].value,vm.runInContext('retentionToday()',context));
"""
    result=subprocess.run([node,'-e',program],input=json.dumps({'script':script,'ids':re.findall(r'id="([^"]+)"',template)}).encode(),
                          capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr.decode('utf8',errors='replace')


def dashboard_runtime(assertions, rows):
    """Exercise the actual embedded script, including filters, charts and exports."""
    import re
    node=shutil.which('node')
    if not node:pytest.skip('Node is needed to execute the dashboard JavaScript')
    template=(ROOT/'scripts/dashboard_view.html').read_text(encoding='utf8')
    program=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const input=JSON.parse(fs.readFileSync(0,'utf8')),controls={},exports=[];
for(const id of input.ids)controls[id]={value:['kind','category','quality','month','source-filter','status-filter'].includes(id)?'all':id==='sort'?'date_desc':id==='page-size'?'25':'',events:{},attrs:{},addEventListener(type,fn){this.events[type]=fn;},setAttribute(key,value){this.attrs[key]=value;},focus(){this.focused=true;}};
controls['bookkeeping-data'].textContent=JSON.stringify({rows:input.rows,gaps:[],source_sha256:'0'.repeat(64),homeoffice:[{year:2012,days:1,amount_cents:600}],retention:{documents:0,unknown:0,groups:[]}});
const context={controls,exports,assert,document:{getElementById:id=>controls[id],body:{addEventListener(){}},createElement(){return {click(){exports.at(-1).filename=this.download;}};}},Blob:class{constructor(parts){this.text=parts.join('');}},URL:{createObjectURL(blob){exports.push({csv:blob.text});return 'blob:synthetic';},revokeObjectURL(){}},setTimeout(fn){fn();}};
vm.createContext(context);vm.runInContext(input.script,context);vm.runInContext(input.assertions,context);
"""
    result=subprocess.run([node,'-e',program],input=json.dumps({'script':template.split('<script>')[1].split('</script>')[0],
        'ids':re.findall(r'id="([^"]+)"',template),'rows':rows,'assertions':assertions}).encode(),capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr.decode('utf8',errors='replace')


@pytest.fixture
def experience_rows():
    def public(number,kind,date,gross,flows,**extra):
        return dict(ref='synthetic-'+number,date=date,kind=kind,number=number,proposed_number=None,
            document_type=kind,related_number=None,status='paid' if kind=='invoice' else 'recorded',
            gross_cents=gross,net_cents=gross,vat_cents=0,vat_rates=[0],tax_treatment='small_business_exempt',
            expense_category='postage' if kind.startswith('expense') else None,coverage='complete',source='imported',
            flows=[dict(ref=number,date=day,amount_cents=amount,bucket=bucket,origin='imported') for day,amount,bucket in flows],
            warnings=[],document_effect_cents=gross,**extra)
    rows=[public('0001','invoice','2011-12-28',11900,[('2012-01-03',11900,'income')]),
          public('0002','invoice','2012-01-02',20000,[('2012-01-04',20000,'income')]),
          public('0003','invoice','2012-01-05',11900,[('2012-02-01',-11900,'income')]),
          public('0004','expense','2012-01-02',5000,[('2012-01-10',-5000,'expense')]),
          public('0005','expense_credit','2012-02-01',-1000,[('2012-02-03',1000,'expense')]),
          public('0006','expense',None,None,[])]
    rows[1].update(coverage='missing',warnings=['Synthetic verification warning'])
    rows[2].update(status='cancelled',document_effect_cents=0)
    rows[4].update(source='local',document_type='supplier_credit',related_number='0004')
    rows[5].update(coverage='missing',expense_category=None)
    return rows


def test_experience_payment_periods_reconcile_and_annual_allowance_stays_separate(experience_rows):
    dashboard_runtime(r"""
controls.year.value='2012';controls.month.value='01';render();
assert.deepStrictEqual(Array.from(filtered.map(r=>r.number)).sort(),['0001','0002','0003','0004']);
assert.strictEqual(visibleFlows.reduce((n,f)=>n+f.amount_cents,0),26900);
assert.strictEqual(controls.income.textContent,money(31900));
assert.strictEqual(controls.expenses.textContent,money(5000));
assert.strictEqual(controls.profit.textContent,money(26900));
assert.strictEqual(annualEur().surplus,15400); // full year 20000 income - 4000 expenses - 600 noncash allowance
assert.strictEqual(periodValues(visibleFlows).reduce((n,v)=>n+v.income-v.expense,0),26900);
assert.strictEqual(expenseGroups(filtered).reduce((n,g)=>n+g[1],0),5000);
controls.month.value='02';render();
assert.strictEqual(controls.income.textContent,money(-11900));
assert.strictEqual(controls.expenses.textContent,money(-1000));
assert.strictEqual(controls.profit.textContent,money(-10900));
assert.strictEqual(annualEur().surplus,15400);
assert(controls['category-chart'].innerHTML.includes('background:#a04336'));
assert(controls['cumulative-chart'].innerHTML.includes(money(-10900)));
""",experience_rows)


def test_experience_numeric_sort_unknown_amounts_and_invalid_filters(experience_rows):
    dashboard_runtime(r"""
clearSelection();controls.sort.value='amount_asc';render();
assert.deepStrictEqual(Array.from(filtered.map(r=>r.number)),['0005','0004','0001','0003','0002','0006']);
assert(controls.rows.innerHTML.includes('—'));
controls.sort.value='amount_desc';render();assert.strictEqual(filtered.at(-1).number,'0006');
controls['amount-min'].value='-10,00';controls['amount-max'].value='50.00';render();
assert.deepStrictEqual(Array.from(filtered.map(r=>r.number)).sort(),['0004','0005']);
controls['amount-min'].value='50,001';render();assert.strictEqual(filtered.length,0);
assert(controls.scope.textContent.includes('Nachkommastellen'));
controls['amount-min'].value='51';render();assert(filterError().includes('Mindestbetrag'));
controls['amount-min'].value='';controls['amount-max'].value='';controls['date-from'].value='2012-02-01';controls['date-to'].value='2012-01-01';render();assert(filterError().includes('Startdatum'));
clearSelection();controls.quality.value='unknown';render();assert.strictEqual(filtered[0].number,'0006');
assert.strictEqual(parseAmount('900719925474100'),NaN);
""",experience_rows)


def test_experience_drilldowns_navigation_and_sorted_export_use_same_selection(experience_rows):
    dashboard_runtime(r"""
controls.year.value='2012';controls.month.value='all';render();
controls['quick-cancel'].onclick();assert.strictEqual(filtered.length,1);assert.strictEqual(filtered[0].number,'0003');
assert.strictEqual(controls['view-records'].hidden,false);assert.strictEqual(controls['nav-records'].attrs['aria-selected'],'true');
controls['records-all'].onclick();
controls['category-chart'].onclick({target:{closest:()=>({dataset:{category:'postage'}})}});
assert.deepStrictEqual(Array.from(filtered.map(r=>r.number)).sort(),['0004','0005']);
controls['sort-amount'].onclick();assert.strictEqual(filtered[0].number,'0004');
controls.csv.onclick();assert.strictEqual(exports.length,1);
assert(exports[0].csv.indexOf('"0004"')<exports[0].csv.indexOf('"0005"'));
assert(!exports[0].csv.includes('"0001"'));assert(exports[0].csv.includes('"-10,00"'));
controls['eur-csv'].onclick();
// The source income is 200 EUR: 119+200-119, annual surplus 154 EUR.
assert(exports[1].csv.includes('"2012";"200,00";"40,00";"6,00";"46,00";"154,00"'));
controls['filter-chips'].onclick({target:{closest:()=>({dataset:{clear:'category'}})}});assert.strictEqual(controls.category.value,'all');
controls.chart.onclick({type:'click',target:{closest:()=>({dataset:{period:'02'}})}});assert.strictEqual(controls.month.value,'02');
controls['header-to-controls'].onclick();assert.strictEqual(controls['view-controls'].hidden,false);assert.strictEqual(controls['new-entry-panel'].open,true);
controls.reset.onclick();assert.strictEqual(controls.month.value,'all');assert.strictEqual(controls.category.value,'all');
""",experience_rows)


def test_experience_csv_exports_all_pages_and_snapshot_is_unchanged(experience_rows):
    rows=[dict(experience_rows[0],ref=f'synthetic-{i}',number=f'{i:04}') for i in range(57)]
    dashboard_runtime(r"""
const before=JSON.stringify(DATA);controls.year.value='all';controls.sort.value='number_asc';render();
assert(controls['page-info'].textContent.startsWith('1–25'));
controls.next.onclick();assert(controls['page-info'].textContent.startsWith('26–50'));
controls.csv.onclick();assert.strictEqual(exports[0].csv.split('\r\n').length,58);
controls['page-size'].value='100';controls['page-size'].events.change();assert(controls['page-info'].textContent.startsWith('1–57'));
assert.strictEqual(JSON.stringify(DATA),before);
""",rows)


def test_procedure_is_embedded_from_matching_staged_source(staged_repo):
    repo,archive,git=staged_repo
    from bs4 import BeautifulSoup
    source=repo/'docs/verfahrensdokumentation.md'
    page=BeautifulSoup((repo/'dashboard.html').read_bytes(),'html.parser')
    assert page.select_one('#procedure-document article h1').get_text()=='Verfahrensdokumentation der lokalen Belegablage'
    assert sha(source.read_bytes()) in page.select_one('#procedure-document').get_text()
    assert len(page.select('#procedure-document table'))>=2
    contents=page.select('#procedure-document .procedure-toc a[href]')
    assert len(contents)>=4 and all(page.find(id=link['href'][1:]) for link in contents)
    assert 'Private betriebliche Ergänzung fehlt' in page.get_text()
    source.write_bytes(source.read_bytes()+b'\n## Synthetic new process\n\nPreserved procedure update.\n')
    with pytest.raises(ValueError,match='nicht vorgemerkte'):
        SCRIPT['build'](repo,tool=repo,staged=True,check=True)
    git('add','docs/verfahrensdokumentation.md')
    SCRIPT['build'](repo,tool=repo,staged=True)
    SCRIPT['build'](repo,tool=repo,staged=True,check=True)
    assert b'Preserved procedure update.' in (repo/'dashboard.html').read_bytes()
    assert sha(source.read_bytes()).encode() in (repo/'dashboard.html').read_bytes()


def test_private_operating_contents_never_enter_dashboard(staged_repo):
    repo,archive,git=staged_repo
    private=repo/'verfahrensdokumentation.md';private.write_text('PRIVATE NAME AND ADDRESS',encoding='utf8')
    git('add','verfahrensdokumentation.md');SCRIPT['build'](repo,tool=repo,staged=True)
    rendered=(repo/'dashboard.html').read_bytes()
    assert b'href="verfahrensdokumentation.md"' in rendered
    assert b'PRIVATE NAME' not in rendered
    private.write_text('SECRET UNSTAGED OPERATING DETAILS',encoding='utf8')
    SCRIPT['build'](repo,tool=repo,staged=True,check=True)
    assert (repo/'dashboard.html').read_bytes()==rendered
    git('reset','--','verfahrensdokumentation.md')
    SCRIPT['build'](repo,tool=repo,staged=True)
    assert b'href="verfahrensdokumentation.md"' not in (repo/'dashboard.html').read_bytes()


def test_initial_operating_document_commit_precedes_archive_initialization(tmp_path):
    repo=tmp_path/'data';repo.mkdir()
    def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.PIPE)
    git('init')
    (repo/'verfahrensdokumentation.md').write_text('Synthetic initial operating document',encoding='utf8')
    git('add','verfahrensdokumentation.md')
    assert SCRIPT['build'](repo,tool=repo,staged=True)=={'skipped':True}
    assert not (repo/'dashboard.html').exists()


def test_procedure_renderer_escapes_html_and_keeps_links_passive():
    from autobookkeeping.dashboard import procedure_document
    from bs4 import BeautifulSoup
    source=b'# Procedure <script>bad()</script>\n\n[unsafe](javascript:bad) [source](https://example.invalid/source)\n\n```html\n<img src="remote" onerror="bad()">\n```\n\n**Check** and `code`'
    page=BeautifulSoup(procedure_document(source),'html.parser')
    assert page.select('script,img,iframe,link')==[]
    links=page.select('a[href]');assert len(links)==1
    assert links[0]['href']=='https://example.invalid/source' and links[0]['rel']==['noopener','noreferrer']
    assert page.select_one('strong').get_text()=='Technik und tatsächlicher Betrieb gehören zusammen.'
    assert '<img src="remote"' in page.select_one('pre').get_text()
    template=(ROOT/'scripts/dashboard_view.html').read_bytes()
    data=html({'literal':'__BOOKKEEPING_PROCEDURE__'},template,b'# __BOOKKEEPING_DATA__')
    public=json.loads(data.decode().split('<script id="bookkeeping-data" type="application/json">')[1].split('</script>')[0])
    assert public['literal']=='__BOOKKEEPING_PROCEDURE__'
    assert b'<h1 id="procedure-part-0">__BOOKKEEPING_DATA__</h1>' in data


def test_procedure_tab_navigation_and_keyboard_wrap():
    dashboard_runtime(r"""
controls['nav-procedure'].onclick();assert.strictEqual(controls['view-procedure'].hidden,false);
assert.strictEqual(controls['view-overview'].hidden,true);assert.strictEqual(controls['nav-procedure'].attrs['aria-selected'],'true');
controls['nav-procedure'].events.keydown({key:'ArrowRight',preventDefault(){}});
assert.strictEqual(controls['view-overview'].hidden,false);
controls['nav-overview'].events.keydown({key:'End',preventDefault(){}});
assert.strictEqual(controls['view-procedure'].hidden,false);
controls['archive-to-procedure'].onclick();assert.strictEqual(controls['view-procedure'].hidden,false);
""",[])
