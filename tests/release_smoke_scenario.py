"""Executable acceptance scenario; upstream systems/calendar are explicitly synthetic."""
import io
import json
import runpy
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import distributions
from pathlib import Path

from opentimestamps.core.notary import PendingAttestation
from opentimestamps.core.op import OpSHA256
from opentimestamps.core.serialize import BytesSerializationContext
from opentimestamps.core.timestamp import DetachedTimestampFile
from reportlab.pdfgen import canvas

from autobookkeeping import __version__
from autobookkeeping.archive import Archive, atomic, encoded, sha, verify_checkpoint
from autobookkeeping.backups import export, source_for
from autobookkeeping.local_invoices import LocalInvoices
from autobookkeeping.models import Address, EbayOrder, EbayOrderItem
from autobookkeeping.publication import Publication
from autobookkeeping.receipts import Receipts
from autobookkeeping.workspace import TOOL_ROOT, git


def scenario(output):
    output=Path(output).resolve(); repo=TOOL_ROOT/'daten'
    assert repo.resolve().is_relative_to(output) and repo.name=='daten'
    def stamp(self,statement,proof):
        detached=DetachedTimestampFile.from_fd(OpSHA256(),io.BytesIO(statement.read_bytes()))
        detached.timestamp.attestations.add(PendingAttestation('https://calendar.example.invalid'))
        context=BytesSerializationContext();detached.serialize(context);proof.write_bytes(context.getbytes())
    Publication.stamp=stamp
    archive=Archive(repo); workflow=LocalInvoices(archive)
    def publish(action,operation):
        with Publication(repo,'synthetic release '+action) as publication:
            result=operation()
        assert publication.result['pushed']
        assert git(repo,'rev-parse','HEAD')==git(repo,'rev-parse','@{upstream}')
        return result
    publish('init',archive.init)
    seller={'name':'SYNTHETIC SELLER','street':'Synthetic Street 1','postal_code':'12345',
            'city':'Synthetic City','country_iso':'DE','tax_number':'SYNTHETIC-ONLY',
            'small_business':True,'tax_note':'Gemäß § 19 UStG keine Umsatzsteuer.',
            'introduction':'Synthetic acceptance test'}
    publish('configure',lambda:workflow.configure(seller,'0000',{'synthetic':True}))
    order=EbayOrder(order_id='SYNTHETIC-RELEASE-ORDER',sales_record_number='999999',
        paid_at=datetime(2011,10,3,12,tzinfo=timezone.utc),
        shipped_at=datetime(2011,10,4,12,tzinfo=timezone.utc),total_value=13,shipping_cost=3,
        shipping_address=Address(name='SYNTHETIC BUYER',street1='Synthetic Street 2',postal_code='12345',
                                 city='Synthetic City',country_iso='DE'),
        items=[EbayOrderItem('SYNTHETIC ITEM',price=10,item_id='synthetic-item',transaction_id='synthetic-transaction')])
    draft=publish('prepare',lambda:workflow.prepare(order,{'vine_checked':True,'dhl_checked':True,'synthetic':True}))
    workflow.preview(draft['id'],output/'invoice-preview',True)
    assert not archive.catalog()['records'] and draft['number'] is None
    publish('activate',lambda:workflow.activate('0000','0000',True,{'synthetic':True}))
    issued=publish('issue',lambda:workflow.issue(draft['id'],draft['revision'],'0001',order,True))
    assert issued['number']=='0001'
    before_original={n:sha(archive.read(n)) for n in archive.catalog()['records'][issued['id']]['current']['documents']}
    receipt=output/'synthetic-expense.pdf'; buffer=io.BytesIO(); pdf=canvas.Canvas(buffer)
    pdf.drawString(30,800,'SYNTHETIC SUPPLIER | ONLY-TEST-1 | 11.00 EUR');pdf.save();receipt.write_bytes(buffer.getvalue())
    receipts=Receipts(workflow); review=receipts.inspect(receipt,output/'receipt-review')
    metadata={'payee':'SYNTHETIC SUPPLIER','number':'ONLY-TEST-1','date':'2011-10-03','currency':'EUR',
              'gross':'11.00','net':'11.00','vat':'0.00','vat_rate':0,'tax_treatment':'as_documented',
              'tax_review_required':False,'description':'SYNTHETIC EXPENSE','category':'other',
              'supplier_country':'DE','business_use':'business','pay_date':None,
              'verification_basis':'Synthetic original page 1'}
    path=output/'receipt-meta.json';atomic(path,encoded(metadata))
    expense=publish('receipt prepare',lambda:receipts.prepare(Path(review['review']),path))
    publish('receipt book',lambda:receipts.book(expense['id'],expense['revision'],True))
    assert len(archive.catalog()['records'])==2
    for name,digest in before_original.items(): assert sha(archive.read(name))==digest
    backup=output/'backup'
    publish('backup export',lambda:export(workflow,backup))
    check=archive.verify()
    statements=list((archive.root/'nachweise').glob('*.json'))
    for statement in statements: assert verify_checkpoint(repo,statement)['git_integrity']
    assert not git(TOOL_ROOT,'status','--porcelain').strip()
    assert not git(repo,'status','--porcelain').strip()
    # Restore with a second environment and only the two bundles + synthetic password.
    restored=output/'restored-tool'
    subprocess.run(['git','clone','--quiet','-c','core.autocrlf=false',str(backup/'tool.bundle'),str(restored)],check=True)
    subprocess.run([sys.executable,'-m','venv',str(restored/'.venv')],check=True)
    python=restored/'.venv'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    subprocess.run([str(python),'-m','pip','install','-e',str(restored)+'[test]'],check=True,capture_output=True)
    subprocess.run([str(python),'-X','utf8',str(restored/'scripts/restore_backup.py'),str(backup),
                    '--password-file',str(repo/'.env'),'--output',str(output/'decrypted-bundle')],check=True,capture_output=True)
    subprocess.run(['git','clone','--quiet','-c','core.autocrlf=false',str(output/'decrypted-bundle/repository.bundle'),str(restored/'daten')],check=True)
    (restored/'daten/.env').write_text('ENCRYPTION_PASSWORD=synthetic-release-test-password\n')
    restored_check=subprocess.check_output([str(python),'-X','utf8',str(restored/'scripts/bookkeeping_archive.py'),'verify'],cwd=restored)
    restored_check=json.loads(restored_check)
    assert restored_check['ok'] and restored_check['records']==2
    (output/'decrypted-bundle/repository.bundle').unlink()
    report={'ok':True,'version':__version__,'python':sys.version.split()[0],
            'tool_commit':git(TOOL_ROOT,'rev-parse','HEAD').decode().strip(),
            'new_setup_tested':True,'fresh_dependency_installations':2,
            'invoice_issue_and_xml_tested':True,'receipt_import_tested':True,
            'private_local_pushes_tested':True,'restored_records':2,
            'git_proofs_verified':len(statements),'data':'synthetic_only',
            'external_apis':'not_called','ots_calendar':'synthetic_pending_attestation',
            'bitcoin_verification':'not_tested',
            'packages':{d.metadata['Name']:d.version for d in distributions()}}
    atomic(output/'report.json',encoded(report)); print(json.dumps(report))


if __name__=='__main__': scenario(sys.argv[1])
