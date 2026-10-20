import copy
import csv
import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
import pytest

from autobookkeeping.archive import Archive, sha
from autobookkeeping.datev_export import projection, files, export, COLUMNS, fields
from autobookkeeping.datev_validation import validate

ROOT = Path(__file__).resolve().parents[1]


def catalog():
    def row(rid, kind, number, gross, **extra):
        return dict(id=rid, kind=kind, source='synthetic-import', source_id=rid, number=number,
            gross=gross, net=gross, vat='0.00', vat_rate=0, year='2026', date='2026-01-01',
            status='issued' if kind in ('invoice','credit_note') else 'recorded', currency='EUR',
            coverage='complete', documents=[], **extra)
    income=row('PRIVATE-INVOICE','invoice','0001','100.00',small_business=True,
        source_detail={'smallBusiness':True,'payments':[{'id':1,'type':'payment','amount':'60.00','date':'2026-01-02T12:00:00Z'},
                                                     {'id':2,'type':'payment','amount':'40.00','date':'2026-02-02T12:00:00Z'}]})
    expense=row('PRIVATE-EXPENSE','expense','PRIVATE SUPPLIER NUMBER','12.00',pay_date='2026-01-03',
                category='office',business_use='business',supplier_country='DE',payee='PRIVATE SUPPLIER')
    refund=row('PRIVATE-REFUND','credit_note','0002','-20.00',original_id=income['id'],original_number='0001',small_business=True)
    supplier=row('PRIVATE-CREDIT','expense_credit','PRIVATE CREDIT','-5.00',original_id=expense['id'],original_number=expense['number'],
                 pay_date='2026-02-04',paid_amount='5.00',payee='PRIVATE SUPPLIER')
    records={r['id']:{'current':r,'history':[]} for r in (income,expense,refund,supplier)}
    return {'records':records,'documents':{},'imports':[],
        'cash_source_overrides':{refund['id']:{'complete':True}},
        'cash_events':{'refund':{'record_id':refund['id'],'amount':'-20.00','date':'2026-02-05','bucket':'income'}},
        'homeoffice_allowances':{}}


def with_allowance(data):
    from autobookkeeping.homeoffice import calculate
    row=dict(calculate(2026,210),eligibility_confirmed=True,basis='SYNTHETIC DAY LIST',updated_at='2026-10-01T00:00:00+00:00')
    data['homeoffice_allowances']={'2026':{'current':row,'history':[]}}
    return data


def test_cash_only_signs_partial_payments_refunds_and_non_cash_allowance():
    source=with_allowance(catalog());before=copy.deepcopy(source);view=projection(source)
    assert source==before
    assert len(view['entries'])==6 and view['issues']==[]
    assert 'PRIVATE' not in json.dumps(view) and 'SYNTHETIC DAY LIST' not in json.dumps(view)
    data=files(view,2026,'1234','7','0'*64,'20261021123456000')
    assert 'EXTF_Pauschalen_2026.csv' in data
    bookings=list(csv.reader(io.StringIO(data['EXTF_Buchungsstapel_2026.csv'].decode('cp1252')),delimiter=';'))
    assert len(bookings)==7 and all(len(line)==125 for line in bookings[1:])
    assert bookings[0][:5]==['EXTF','700','21','Buchungsstapel','13']
    assert bookings[0][10:16]==['1234','7','20260101','4','20260101','20261231']
    entries=bookings[2:]
    assert [(r[0],r[1]) for r in entries if r[6]=='8192']==[('60,00','H'),('40,00','H'),('20,00','S')]
    assert [(r[0],r[1]) for r in entries if r[6]=='4930']==[('12,00','S'),('5,00','H')]
    assert all(r[7]=='1371' and r[8]=='' and r[41]=='K' and r[113]=='0' for r in entries)
    note=json.loads(data['exportbericht.json']);assert (note['income_cents'],note['expense_cents'],note['allowance_cents'])==(8000,700,126000)
    allowance=list(csv.reader(io.StringIO(data['EXTF_Pauschalen_2026.csv'].decode('cp1252')),delimiter=';'))
    assert allowance[0][18]=='2' and allowance[2][0:2]==['1260,00','S'] and allowance[2][6:8]==['4287','1371']
    assert validate(data['EXTF_Buchungsstapel_2026.csv'])['rows']==5
    hashes=json.loads(data['pruefsummen.json']);assert all(sha(data[name])==digest for name,digest in hashes.items())


def test_unresolved_entries_never_silently_become_valid_bookings():
    source=catalog();expense=source['records']['PRIVATE-EXPENSE']['current']
    expense['business_use']='mixed'
    source['records']['PRIVATE-INVOICE']['current']['source_detail']['payments'][0]['cancellationPaymentId']=33
    view=projection(source)
    assert {'private_share','payment_unclear'} <= {i['reason'] for i in view['issues']}
    assert len(view['entries'])==1  # verified refund only; supplier inherits private-use exception
    report=json.loads(files(view,2026,'1234','7','0'*64)['exportbericht.json'])
    assert not report['complete_for_recorded_year'] and len(report['excluded'])==4
    source=catalog();source['records']['PRIVATE-INVOICE']['current']['small_business']=False
    source['records']['PRIVATE-INVOICE']['current']['source_detail']['smallBusiness']=False
    assert 'tax_scope' in {i['reason'] for i in projection(source)['issues']}


def test_wrong_debit_credit_direction_is_rejected_before_serializing():
    view=projection(catalog());view['entries'][0]['side']='S'
    with pytest.raises(ValueError,match='Kontenzuordnung'):files(view,2026,'1234','7','0'*64)


@pytest.mark.parametrize('advisor,client,year',[('','7',2026),('1000','7',2026),('1234','0',2026),('1234','0007',2026),('1234','7',2025)])
def test_no_invented_target_identifiers_or_unreviewed_year(advisor,client,year):
    with pytest.raises(ValueError):files(projection(catalog()),year,advisor,client,'0'*64)


@pytest.mark.parametrize('mutation', ['negative','zero','date','columns','tax','duplicate','newline','version'])
def test_independent_validator_rejects_malformed_files(mutation):
    data=files(projection(catalog()),2026,'1234','7','0'*64)['EXTF_Buchungsstapel_2026.csv']
    lines=data.decode('cp1252').splitlines();row=list(csv.reader([lines[2]],delimiter=';'))[0]
    if mutation=='negative':lines[2]=lines[2].replace('60,00;','-60,00;',1)
    if mutation=='zero':lines[2]=lines[2].replace('60,00;','0,00;',1)
    if mutation=='date':lines[2]=lines[2].replace(';0201;',';3102;',1)
    if mutation=='columns':lines[2]+=';'
    if mutation=='tax':lines[2]=lines[2].replace(';"K";',';"I";')
    if mutation=='duplicate':lines.append(lines[2])
    if mutation=='version':lines[0]=lines[0].replace(';700;',';701;',1)
    malformed=('\r\n'.join(lines)+'\r\n').encode('cp1252')
    if mutation=='newline':malformed=malformed.replace(b'\r\n',b'\n')
    with pytest.raises(ValueError):validate(malformed)


def test_browser_download_zip_matches_python_csv_and_independent_parser():
    node=shutil.which('node')
    if not node:pytest.skip('Node required')
    source=(ROOT/'scripts/dashboard_view.html').read_text(encoding='utf8')
    script='function datevLine'+source.split('function datevLine',1)[1].split('function datevDownload',1)[0]
    snapshot=projection(with_allowance(catalog()));at='20261021123456000'
    program=r"""
const vm=require('vm'),fs=require('fs'),assert=require('assert'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const context={TextEncoder,Uint8Array,DataView,crypto:require('crypto').webcrypto};vm.createContext(context);vm.runInContext(input.script,context);
(async()=>{
 for(const args of [['','7'],['1234','0']])await assert.rejects(context.makeDatevFiles(input.snapshot,2026,...args,'0'.repeat(64),input.at));
 const files=await context.makeDatevFiles(input.snapshot,2026,'1234','7','0'.repeat(64),input.at);
 process.stdout.write(Buffer.from(context.datevZip(files)).toString('base64'));
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result=subprocess.run([node,'-e',program],input=json.dumps({'script':script,'snapshot':snapshot,'at':at}).encode(),capture_output=True,check=True,timeout=20)
    import base64
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result.stdout))) as archive:
        assert archive.testzip() is None
        expected=files(snapshot,2026,'1234','7','0'*64,at)
        for name in ('EXTF_Buchungsstapel_2026.csv','EXTF_Pauschalen_2026.csv'):
            actual=archive.read(name);assert actual==expected[name];assert validate(actual)['ok']
        hashes=json.loads(archive.read('pruefsummen.json'));assert all(sha(archive.read(name))==digest for name,digest in hashes.items())
        note=json.loads(archive.read('exportbericht.json'));assert note['income_cents']==8000 and note['allowance_cents']==126000


def test_dashboard_export_dialog_checks_target_ids_and_clears_them_on_close():
    node=shutil.which('node')
    if not node:pytest.skip('Node required')
    source=(ROOT/'scripts/dashboard_view.html').read_text(encoding='utf8')
    script='function datevLine'+source.split('function datevLine',1)[1].split("$('basis').textContent",1)[0]
    program=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const controls={},blobs=[],$=id=>controls[id]||(controls[id]={value:'',events:{},addEventListener(e,f){this.events[e]=f},showModal(){this.open=true},close(){this.open=false;this.events.close?.()}});
$('year').value='2026';$('datev-year').value='2026';
const context={$,DATA:{datev_export:input.snapshot,source_sha256:'0'.repeat(64)},esc:String,python:'buchhaltung ',psQuote:v=>"'"+v.replace(/'/g,"''")+"'",
 TextEncoder,Uint8Array,DataView,Blob,crypto:require('crypto').webcrypto,URL:{createObjectURL(b){blobs.push(b);return 'blob:synthetic'},revokeObjectURL(){}},
 setTimeout(){},document:{createElement(){return {click(){}}}}};
vm.createContext(context);vm.runInContext(input.script,context);
(async()=>{
 $('open-datev').onclick();assert($('datev-dialog').open);assert($('datev-summary').textContent.includes('5 Zahlungszeilen'));
 await $('datev-download').onclick();assert.strictEqual(blobs.length,0);assert($('datev-result').textContent.includes('Beraternummer'));
 $('datev-advisor').value='1234';$('datev-client').value='7';await $('datev-download').onclick();
 assert.strictEqual(blobs.length,1);assert($('datev-result').textContent.includes('heruntergeladen'));
 $('datev-dialog').close();assert.strictEqual($('datev-advisor').value,'');assert.strictEqual($('datev-client').value,'');
 assert.strictEqual($('datev-cli').textContent,'');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    subprocess.run([node,'-e',program],input=json.dumps({'script':script,'snapshot':projection(with_allowance(catalog()))}).encode(),
                   capture_output=True,check=True,timeout=20)


def test_read_only_export_outside_repo_without_publication(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir();archive=Archive(root,'synthetic-password');archive.init()
    # Store an ordinary receipt through the public import; no new financial document is issued.
    pdf=tmp_path/'synthetic.pdf';pdf.write_bytes(b'%PDF-1.4 SYNTHETIC')
    metadata=tmp_path/'synthetic.json';metadata.write_text(json.dumps(dict(source='synthetic',source_id='expense',kind='expense',
        date='2026-01-02',pay_date='2026-01-02',currency='EUR',gross='3.00',net='3.00',vat='0.00',vat_rate=0,
        category='postage',status='recorded')),encoding='utf8')
    archive.import_local(metadata,[pdf])
    before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    from autobookkeeping.publication import Publication
    monkeypatch.setattr(Publication,'__enter__',lambda self:pytest.fail('Export must not publish'))
    result=export(archive,2026,'1234','7',tmp_path/'export')
    assert result['data_changed'] is False and not result['datev_application_tested']
    with zipfile.ZipFile(result['output']) as package:assert validate(package.read('EXTF_Buchungsstapel_2026.csv'))['rows']==1
    assert before=={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError):export(archive,2026,'1234','7',root/'output')
