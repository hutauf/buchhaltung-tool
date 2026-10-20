import copy
import json
from pathlib import Path
import pytest
from autobookkeeping.archive import Archive, sha
from autobookkeeping.annual_report import report, export


def test_year_is_payment_based_and_export_keeps_other_years_and_histories(tmp_path, monkeypatch):
    root=tmp_path/'repo';root.mkdir();archive=Archive(root,'synthetic-password');archive.init()
    original=tmp_path/'original.pdf';original.write_bytes(b'%PDF-1.4 SYNTHETIC ORIGINAL')
    metadata=tmp_path/'metadata.json'
    metadata.write_text(json.dumps({'source':'synthetic','source_id':'one','kind':'invoice','date':'2010-12-30',
        'gross':'12.00','net':'12.00','vat':'0.00','vat_rate':0,'status':'issued','currency':'EUR','number':'0001'}),encoding='utf8')
    archive.import_local(metadata,[original])
    catalog=archive.catalog();rid=next(iter(catalog['records']))
    row=catalog['records'][rid]['current'];row['source_detail']={'payments':[{'id':'test','type':'payment','amount':'12.00','date':'2011-01-02T12:00:00Z'}]}
    catalog['records'][rid]['history']=[copy.deepcopy(row)]
    archive.save_catalog(catalog)
    before=(archive.root/'database.json.enc').read_bytes()
    annual=report(catalog,2011)
    assert annual['summary']['income_cents']==1200 and len(annual['records'])==1
    assert report(catalog,2010)['summary']['income_cents']==0
    # Export must not call the publication pipeline or any network timestamp client.
    from autobookkeeping import publication
    monkeypatch.setattr(publication.Publication,'__enter__',lambda self:pytest.fail('read-only report published data'))
    result=export(archive,2011,tmp_path/'export')
    target=Path(result['directory'])
    assert result['complete'] and not result['tax_return_ready']
    assert (target/'jahresbericht.html').is_file() and (target/'data-description.json').is_file()
    assert json.loads((target/'catalog.json').read_bytes())['records'][rid]['history']
    assert len(json.loads((target/'export-manifest.json').read_bytes())['documents'])==1
    assert '2011-01-02' in (target/'jahreszahlungen.csv').read_text(encoding='utf8')
    hashes=json.loads((target/'jahresbericht-manifest.json').read_bytes())
    assert all(sha((target/name).read_bytes())==digest for name,digest in hashes.items())
    assert before==(archive.root/'database.json.enc').read_bytes()
    with pytest.raises(ValueError):export(archive,2011,root/'plaintext')
    with pytest.raises(ValueError):report(catalog,'2011<script>')
